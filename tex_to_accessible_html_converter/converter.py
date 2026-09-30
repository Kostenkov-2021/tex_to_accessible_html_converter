"""Convert LaTeX documents to HTML with MathML for MathCAT.

The converter delegates TeX parsing to TeX4ht via ``make4ht`` and then applies
a small compatibility pass that makes every generated ``<math>`` element an
explicit MathML element.
"""

from __future__ import annotations

import fnmatch
import html as html_lib
import math
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import tex_compatibility
from conversion_process import run_logged_process
from mathml_fidelity import repair_mathml_fidelity
from mathml_validation import validate_mathml_structure
from tex_compatibility import (
    MATHML_CONFIG,
    adapt_cfrac_for_tex4ht,
    adapt_literal_relations_for_tex4ht,
    adapt_luatex_unicode_fonts,
    adapt_miktex_paragraphs,
    adapt_multline_for_tex4ht,
    adapt_xetex_cyrillic,
    normalize_prime_superscripts,
    normalize_reference_keys,
)

MIKTEX_PARAGRAPH_COMPAT = tex_compatibility.MIKTEX_PARAGRAPH_COMPAT
XETEX_CYRILLIC_COMPAT = tex_compatibility.XETEX_CYRILLIC_COMPAT


MATHML_NAMESPACE = "http://www.w3.org/1998/Math/MathML"
MATH_TAG_RE = re.compile(r"<math(?P<attrs>\s[^>]*)?>", re.IGNORECASE)
TABLE_TAG_RE = re.compile(r"<table\b[^>]*>", re.IGNORECASE)
CLASS_ATTR_RE = re.compile(
    r"\bclass\s*=\s*(?P<quote>['\"])(?P<value>.*?)(?P=quote)",
    re.IGNORECASE | re.DOTALL,
)
ROLE_ATTR_RE = re.compile(r"\brole\s*=", re.IGNORECASE)
EQUATION_LAYOUT_CLASSES = {"equation", "equation-star"}
FIGURE_RE = re.compile(r"<figure\b[^>]*>.*?</figure>", re.IGNORECASE | re.DOTALL)
FIGCAPTION_TAG_RE = re.compile(r"<figcaption\b[^>]*>", re.IGNORECASE)
TABLE_FRAGMENT_RE = re.compile(r"<table\b[^>]*>.*?</table>", re.IGNORECASE | re.DOTALL)
ROW_RE = re.compile(r"<tr\b[^>]*>.*?</tr>", re.IGNORECASE | re.DOTALL)
OPENING_TAG_ID_RE = re.compile(
    r"\bid\s*=\s*(?P<quote>['\"])(?P<value>.*?)(?P=quote)",
    re.IGNORECASE | re.DOTALL,
)
ARIA_LABELLEDBY_RE = re.compile(r"\baria-labelledby\s*=", re.IGNORECASE)
BODY_RE = re.compile(
    r"(?P<open><body\b[^>]*>)(?P<content>.*?)(?P<close></body\s*>)",
    re.IGNORECASE | re.DOTALL,
)
TOC_BLOCK_RE = re.compile(
    r"(?P<heading><h(?P<level>[1-6])\b[^>]*>.*?</h(?P=level)>)"
    r"(?P<space>\s*)"
    r"(?P<toc><div\b(?=[^>]*\bclass\s*=\s*['\"][^'\"]*"
    r"\btableofcontents\b[^'\"]*['\"])[^>]*>.*?</div>)",
    re.IGNORECASE | re.DOTALL,
)
TEX_DISTRIBUTIONS = ("auto", "texlive", "miktex")


def normalize_heading_levels(html: str) -> str:
    """Remove gaps in TeX4ht's document heading hierarchy.

    TeX4ht commonly emits an article title as ``h1``, sections as ``h3`` and
    subsections as ``h4``.  Screen-reader heading navigation then reports a
    nonexistent level two.  Compress only the levels that are actually used;
    the relative document hierarchy remains unchanged.
    """
    levels = sorted(
        {
            int(match.group(1))
            for match in re.finditer(r"<h([1-6])\b", html, re.IGNORECASE)
        }
    )
    mapping = {level: index + 1 for index, level in enumerate(levels)}
    if all(level == mapped for level, mapped in mapping.items()):
        return html

    return re.sub(
        r"<(?P<slash>/?)h(?P<level>[1-6])(?P<rest>\b)",
        lambda match: (
            f"<{match.group('slash')}h{mapping[int(match.group('level'))]}"
            f"{match.group('rest')}"
        ),
        html,
        flags=re.IGNORECASE,
    )


def ensure_document_title(html: str) -> str:
    """Use the visible document heading as a reliable HTML title.

    Some TeX4ht engine combinations emit an empty title or corrupt Cyrillic
    only inside ``<title>`` even though the visible ``h1`` is correct.
    """
    heading = re.search(r"<h1\b[^>]*>(.*?)</h1\s*>", html, re.IGNORECASE | re.DOTALL)
    title = re.search(r"<title\b[^>]*>.*?</title\s*>", html, re.IGNORECASE | re.DOTALL)
    if heading is None or title is None:
        return html
    plain_title = re.sub(r"<[^>]+>", " ", heading.group(1))
    plain_title = " ".join(html_lib.unescape(plain_title).split())
    if not plain_title:
        return html
    replacement = f"<title>{html_lib.escape(plain_title)}</title>"
    return html[: title.start()] + replacement + html[title.end() :]


class ConversionError(RuntimeError):
    """Raised when TeX4ht cannot produce the expected HTML output."""


def make_mathml_explicit(html: str) -> str:
    """Add explicit MathML namespace attributes to TeX4ht math nodes."""

    def add_namespace(match: re.Match[str]) -> str:
        attrs = match.group("attrs") or ""
        if re.search(r"\sxmlns\s*=", attrs, flags=re.IGNORECASE):
            return match.group(0)
        return f"<math xmlns='{MATHML_NAMESPACE}'{attrs}>"

    return MATH_TAG_RE.sub(add_namespace, html)


def mark_equation_layout_tables(html: str) -> str:
    """Hide TeX4ht's equation layout tables from accessibility APIs.

    Only tables carrying the dedicated `equation` or `equation-star`
    class are marked. Data tables and the MathML nested inside equations are
    left untouched.
    """

    def add_presentation_role(match: re.Match[str]) -> str:
        tag = match.group(0)
        class_match = CLASS_ATTR_RE.search(tag)
        if class_match is None:
            return tag
        classes = set(class_match.group("value").split())
        if not classes & EQUATION_LAYOUT_CLASSES or ROLE_ATTR_RE.search(tag):
            return tag
        return f"{tag[:-1]} role='presentation'>"

    return TABLE_TAG_RE.sub(add_presentation_role, html)


def improve_data_table_accessibility(html: str) -> str:
    """Add headers and caption relationships to TeX4ht data tables.

    TeX4ht identifies LaTeX `tabular` output with the `tabular` class.
    Its separate equation layout tables are intentionally excluded here.
    """

    def is_tabular(opening_tag: str) -> bool:
        class_match = CLASS_ATTR_RE.search(opening_tag)
        return bool(
            class_match and "tabular" in set(class_match.group("value").split())
        )

    def add_attribute(opening_tag: str, attribute: str) -> str:
        return f"{opening_tag[:-1]} {attribute}>"

    def label_captioned_table(match: re.Match[str]) -> str:
        figure = match.group(0)
        caption_match = FIGCAPTION_TAG_RE.search(figure)
        table_match = TABLE_FRAGMENT_RE.search(figure)
        if caption_match is None or table_match is None:
            return figure
        table = table_match.group(0)
        table_tag_match = TABLE_TAG_RE.match(table)
        if table_tag_match is None or not is_tabular(table_tag_match.group(0)):
            return figure

        caption_tag = caption_match.group(0)
        caption_id_match = OPENING_TAG_ID_RE.search(caption_tag)
        if caption_id_match is not None:
            caption_id = caption_id_match.group("value")
        else:
            table_id_match = OPENING_TAG_ID_RE.search(table_tag_match.group(0))
            if table_id_match is None:
                return figure
            caption_id = f"{table_id_match.group('value')}-caption"
            labelled_caption_tag = add_attribute(caption_tag, f"id='{caption_id}'")
            figure = (
                figure[: caption_match.start()]
                + labelled_caption_tag
                + figure[caption_match.end() :]
            )
            table_match = TABLE_FRAGMENT_RE.search(figure)
            if table_match is None:
                return figure
            table = table_match.group(0)
            table_tag_match = TABLE_TAG_RE.match(table)

        assert table_tag_match is not None
        table_tag = table_tag_match.group(0)
        if not ARIA_LABELLEDBY_RE.search(table_tag):
            labelled_table_tag = add_attribute(
                table_tag, f"aria-labelledby='{caption_id}'"
            )
            table = labelled_table_tag + table[table_tag_match.end() :]
            figure = figure[: table_match.start()] + table + figure[table_match.end() :]
        return figure

    def convert_cell(row: str, scope: str, *, all_cells: bool) -> str:
        count = 0 if all_cells else 1
        row, changed = re.subn(
            r"<td\b([^>]*)>",
            rf"<th scope='{scope}'\1>",
            row,
            count=count,
            flags=re.IGNORECASE,
        )
        if changed:
            row = re.sub(
                r"</td>",
                "</th>",
                row,
                count=changed,
                flags=re.IGNORECASE,
            )
        return row

    def improve_table(match: re.Match[str]) -> str:
        table = match.group(0)
        opening_match = TABLE_TAG_RE.match(table)
        if opening_match is None or not is_tabular(opening_match.group(0)):
            return table

        rows = list(ROW_RE.finditer(table))
        data_row_index = 0
        parts = []
        cursor = 0
        for row_match in rows:
            parts.append(table[cursor : row_match.start()])
            row = row_match.group(0)
            class_match = CLASS_ATTR_RE.search(row[: row.find(">") + 1])
            row_classes = (
                set(class_match.group("value").split())
                if class_match is not None
                else set()
            )
            if "array-hline" in row_classes:
                row_tag_match = re.match(r"<tr\b[^>]*>", row, re.IGNORECASE)
                if (
                    row_tag_match
                    and "aria-hidden" not in row_tag_match.group(0).lower()
                ):
                    row = (
                        add_attribute(row_tag_match.group(0), "aria-hidden='true'")
                        + row[row_tag_match.end() :]
                    )
            elif "<th" not in row.lower():
                if data_row_index == 0:
                    row = convert_cell(row, "col", all_cells=True)
                else:
                    row = convert_cell(row, "row", all_cells=False)
                data_row_index += 1
            else:
                data_row_index += 1
            parts.append(row)
            cursor = row_match.end()
        parts.append(table[cursor:])
        return "".join(parts)

    html = FIGURE_RE.sub(label_captioned_table, html)
    return TABLE_FRAGMENT_RE.sub(improve_table, html)


def add_document_landmarks(html: str) -> str:
    """Add main-content and table-of-contents landmarks to TeX4ht HTML."""
    if not re.search(r"<nav\b[^>]*\baria-label\s*=", html, re.IGNORECASE):
        html = TOC_BLOCK_RE.sub(
            r'<nav aria-label="Оглавление">\g<heading>\g<space>\g<toc></nav>',
            html,
            count=1,
        )

    if re.search(r"<main\b", html, re.IGNORECASE):
        return html

    def wrap_body(match: re.Match[str]) -> str:
        return (
            f"{match.group('open')}\n<main>\n"
            f"{match.group('content')}\n"
            f"</main>\n{match.group('close')}"
        )

    return BODY_RE.sub(wrap_body, html, count=1)


def rewrite_css_link(html: str, old_stem: str, new_stem: str) -> str:
    """Update TeX4ht's generated stylesheet link when the output is renamed."""
    if old_stem == new_stem:
        return html
    return html.replace(f"href='{old_stem}.css'", f"href='{new_stem}.css'").replace(
        f'href="{old_stem}.css"', f'href="{new_stem}.css"'
    )


def inline_css(html: str, css: str, css_stem: str) -> str:
    """Replace TeX4ht's stylesheet link with an inline style element."""
    style = f"<style>\n{css}\n</style>"
    patterns = [
        re.compile(
            rf"<link\b(?=[^>]*\bhref='{re.escape(css_stem)}\.css')(?=[^>]*\brel='stylesheet')[^>]*/?\s*>",
            re.IGNORECASE,
        ),
        re.compile(
            rf'<link\b(?=[^>]*\bhref="{re.escape(css_stem)}\.css")(?=[^>]*\brel="stylesheet")[^>]*/?\s*>',
            re.IGNORECASE,
        ),
    ]
    for pattern in patterns:
        html, count = pattern.subn(style, html, count=1)
        if count:
            return html
    return html.replace("</head>", f"{style}\n</head>", 1)


def output_file_for(tex_file: Path, output_dir: Path | None = None) -> Path:
    """Return the HTML output path for a source file and optional output folder."""
    if output_dir is None:
        return tex_file.with_suffix(".html")
    return output_dir / f"{tex_file.stem}.html"


def logs_directory_for(output_file: Path) -> Path:
    """Return the persistent diagnostic-log directory for ``output_file``."""
    return output_file.with_name(output_file.name + ".logs")


def temporary_directory_for(output_file: Path) -> Path:
    """Return the persistent temporary-file directory for ``output_file``."""
    return output_file.with_name(output_file.name + ".temporary")


def save_conversion_logs(build_dir: Path, output_file: Path) -> Path:
    """Copy diagnostic build artifacts and return their unique run directory."""
    destination = logs_directory_for(output_file)
    destination.mkdir(parents=True, exist_ok=True)
    run_dir = Path(tempfile.mkdtemp(prefix="run-", dir=destination))
    for path in build_dir.iterdir():
        if path.is_file() and path.suffix.lower() in {
            ".log",
            ".lg",
            ".txt",
            ".json",
            ".html",
        }:
            shutil.copy2(path, run_dir / path.name)
    return run_dir


def save_temporary_files(build_dir: Path, output_file: Path) -> Path:
    """Copy the complete isolated build tree next to the HTML output."""
    destination = temporary_directory_for(output_file)
    destination.mkdir(parents=True, exist_ok=True)
    run_dir = Path(tempfile.mkdtemp(prefix="run-", dir=destination))
    shutil.copytree(build_dir, run_dir, dirs_exist_ok=True)
    return run_dir


def safe_temp_prefix(stem: str) -> str:
    """Return an ASCII-only prefix for TeX work directories."""
    safe_stem = re.sub(r"[^A-Za-z0-9_.-]+", "-", stem).strip(".-")
    return f"{safe_stem[:48] or 'tex'}-build-"


def is_relative_to(path: Path, parent: Path) -> bool:
    """Return whether ``path`` is located within ``parent``."""
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def stage_source_tree(tex_file: Path, work_dir: Path, build_root: Path) -> Path:
    """Copy the source folder without rewriting any TeX source files.

    The staged tree is deliberately byte-for-byte equivalent to the source
    tree (apart from ignored converter outputs).  Source-level compatibility
    rewrites are unsafe for general TeX because macros and catcodes can change
    the meaning of text that merely looks like a standard LaTeX command.
    """
    source_dir = tex_file.parent
    resolved_build_root = build_root.resolve()
    stale_output_names = {f"{tex_file.stem}.html", f"{tex_file.stem}.css"}

    if work_dir.exists():
        shutil.rmtree(work_dir)

    def ignore_names(directory: str, names: list[str]) -> set[str]:
        current_dir = Path(directory)
        ignored: set[str] = set()
        for name in names:
            candidate = (current_dir / name).resolve()
            is_build_path = candidate == resolved_build_root or is_relative_to(
                candidate, resolved_build_root
            )
            is_stale_output = (
                current_dir.resolve() == source_dir and name in stale_output_names
            )
            is_converter_artifact = name.endswith(
                (".html.logs", ".html.temporary")
            ) or fnmatch.fnmatch(name, f"{tex_file.stem}-build-*")
            if is_build_path or is_stale_output or is_converter_artifact:
                ignored.add(name)
        return ignored

    shutil.copytree(source_dir, work_dir, ignore=ignore_names)
    return work_dir / tex_file.name


def is_miktex_path(path: str) -> bool:
    """Return whether an executable path appears to belong to MiKTeX."""
    return any(
        part == "miktex" or part.startswith("miktex ")
        for part in re.split(r"[/\\]+", str(path).lower())
    )


def miktex_bin_candidates() -> list[Path]:
    """Return common MiKTeX binary folders on Windows."""
    roots = [
        os.environ.get("LOCALAPPDATA"),
        os.environ.get("ProgramFiles"),
        os.environ.get("ProgramFiles(x86)"),
        os.environ.get("APPDATA"),
    ]
    candidates: list[Path] = []
    for root in roots:
        if not root:
            continue
        base = Path(root)
        candidates.extend(
            [
                base / "Programs" / "MiKTeX" / "miktex" / "bin" / "x64",
                base / "MiKTeX" / "miktex" / "bin" / "x64",
                base / "MiKTeX 2.9" / "miktex" / "bin" / "x64",
                base / "MiKTeX" / "miktex" / "bin",
                base / "MiKTeX 2.9" / "miktex" / "bin",
            ]
        )
    return candidates


def find_make4ht(tex_distribution: str = "auto") -> str | None:
    """Find make4ht for TeX Live or MiKTeX."""
    path_match = shutil.which("make4ht")
    if tex_distribution == "texlive":
        if path_match and not is_miktex_path(path_match):
            return path_match
        # MiKTeX may precede TeX Live in PATH. Search the remaining entries,
        # then the standard Windows installation directories.
        candidates = [Path(entry) for entry in os.get_exec_path() if entry]
        if os.name == "nt":
            root = Path(os.environ.get("SystemDrive", "C:") + "/") / "texlive"
            if root.is_dir():
                candidates.extend(sorted(root.glob("*/bin/windows"), reverse=True))
        for directory in candidates:
            if is_miktex_path(str(directory)):
                continue
            for name in ("make4ht.exe", "make4ht"):
                candidate = directory / name
                if candidate.is_file():
                    return str(candidate)
        return None
    if tex_distribution == "auto" and path_match:
        return path_match
    if tex_distribution == "miktex" and path_match and is_miktex_path(path_match):
        return path_match

    executable_names = ["make4ht.exe", "make4ht"]
    for directory in miktex_bin_candidates():
        for executable_name in executable_names:
            candidate = directory / executable_name
            if candidate.is_file():
                return str(candidate)

    if tex_distribution == "miktex":
        return None
    return path_match


def configure_tex_environment(
    env: dict[str, str], build_dir: Path, tex_distribution: str
) -> None:
    """Preserve the TeX distribution's configured package and font caches.

    Both MiKTeX and TeX Live keep generated font metadata in their configured
    user trees.  Pointing these variables at a fresh per-run directory makes
    installed T2A fonts (for example ``larm1200``) appear to be missing.
    The build itself is already isolated by make4ht's output directory.
    """
    return


def run_make4ht(
    tex_file: Path,
    output_dir: Path,
    build_dir: Path,
    engine: str,
    mode: str,
    tex_distribution: str = "auto",
    timeout: float = 300,
) -> subprocess.CompletedProcess[str]:
    """Run make4ht with a local writable TeX cache."""
    make4ht = find_make4ht(tex_distribution)
    if make4ht is None:
        if tex_distribution == "texlive":
            raise ConversionError(
                "TeX Live make4ht was not found. Install TeX Live with TeX4ht support and add its bin directory to PATH."
            )
        if tex_distribution == "miktex":
            raise ConversionError(
                "make4ht was not found. Install MiKTeX with the make4ht and TeX4ht packages."
            )
        raise ConversionError(
            "make4ht was not found. Install TeX Live or MiKTeX with TeX4ht support."
        )

    engine_args = {
        "latex": [],
        "lualatex": ["-l"],
        "xelatex": ["-x"],
    }[engine]

    env = os.environ.copy()
    # make4ht launches TeX engines by name; they must come from the same
    # distribution as make4ht itself.
    env["PATH"] = str(Path(make4ht).parent) + os.pathsep + env.get("PATH", "")
    actual_distribution = "miktex" if is_miktex_path(make4ht) else "texlive"
    configure_tex_environment(env, build_dir, actual_distribution)
    text = tex_file.read_text(encoding="utf-8")
    text = adapt_cfrac_for_tex4ht(text)
    text = adapt_multline_for_tex4ht(text)
    text = adapt_literal_relations_for_tex4ht(text)
    text = normalize_reference_keys(text)
    text = normalize_prime_superscripts(text)
    if actual_distribution == "miktex":
        text = adapt_miktex_paragraphs(text)
    if engine == "lualatex":
        text = adapt_luatex_unicode_fonts(text)
    if engine == "xelatex":
        text = adapt_xetex_cyrillic(text)
    tex_file.write_text(text, encoding="utf-8")

    config = build_dir / "accessible-mathml.cfg"
    config.write_text(MATHML_CONFIG, encoding="utf-8")
    command = [
        make4ht,
        *engine_args,
        "-c",
        str(config).replace("\\", "/"),
        "-f",
        # Our post-processing pipeline performs its own strict MathML repair
        # and validation.  make4ht's common DOM filters fall back to an HTML
        # parser when one formula is problematic; that fallback interprets
        # MathML ``&lt;`` text as markup and corrupts otherwise valid formulas.
        "html5-common_domfilters",
        "-m",
        # Draft mode omits passes needed for the table of contents and can
        # drop forward-referenced formula material. Accessible output must be
        # complete, so retain the UI/API option but use the complete pass set.
        "default" if mode == "draft" else mode,
        "-d",
        str(output_dir),
        "-B",
        str(build_dir),
        tex_file.name,
        "mathml",
    ]

    return run_logged_process(
        command, cwd=tex_file.parent, env=env, log_dir=build_dir, timeout=timeout
    )


def convert_tex_to_accessible_html(
    tex_file: Path,
    output_file: Path | None = None,
    build_dir: Path | None = None,
    engine: str = "lualatex",
    mode: str = "default",
    keep_build: bool = False,
    tex_distribution: str = "auto",
    timeout: float = 300,
    keep_logs: bool = False,
    keep_temporary_files: bool = False,
) -> Path:
    """Convert a ``.tex`` file to HTML containing MathCAT-compatible MathML."""
    if tex_distribution not in TEX_DISTRIBUTIONS:
        raise ConversionError(f"Unknown TeX distribution: {tex_distribution}")
    if engine not in {"lualatex", "xelatex", "latex"}:
        raise ConversionError(f"Unknown TeX engine: {engine}")
    if not math.isfinite(timeout) or timeout <= 0:
        raise ConversionError("The timeout must be a positive finite number.")

    tex_file = tex_file.resolve()
    if not tex_file.is_file():
        raise ConversionError(f"The source file does not exist: {tex_file}")

    output_file = (output_file or tex_file.with_suffix(".html")).resolve()
    output_dir = output_file.parent
    output_dir.mkdir(parents=True, exist_ok=True)

    owns_build_dir = build_dir is None
    if build_dir is None:
        build_dir = Path(tempfile.mkdtemp(prefix=safe_temp_prefix(tex_file.stem)))
    else:
        build_dir = build_dir.resolve()
        build_dir.mkdir(parents=True, exist_ok=True)
    work_dir = build_dir / "source"
    make4ht_dir = build_dir / "make4ht"

    try:
        staged_tex_file = stage_source_tree(tex_file, work_dir, build_dir)
        make4ht_dir.mkdir(parents=True, exist_ok=True)
        result = run_make4ht(
            staged_tex_file,
            make4ht_dir,
            make4ht_dir,
            engine,
            mode,
            tex_distribution,
            timeout=timeout,
        )
        (make4ht_dir / "stdout.txt").write_text(result.stdout, encoding="utf-8")
        (make4ht_dir / "stderr.txt").write_text(result.stderr, encoding="utf-8")
        if result.returncode != 0:
            raise ConversionError(
                "make4ht failed.\n\nProgram output:\n"
                + result.stdout
                + "\nError output:\n"
                + result.stderr
            )
        tex_log = make4ht_dir / f"{tex_file.stem}.log"
        if tex_log.is_file():
            log_text = tex_log.read_text(encoding="utf-8", errors="replace")
            tex_errors = re.findall(r"^!.*$", log_text, flags=re.MULTILINE)
            if tex_errors:
                raise ConversionError(
                    "TeX errors occurred while creating HTML:\n"
                    + "\n".join(tex_errors[:20])
                )
        generated_html = first_existing(
            make4ht_dir / f"{tex_file.stem}.html",
            work_dir / f"{tex_file.stem}.html",
        )
        generated_css = first_existing(
            make4ht_dir / f"{tex_file.stem}.css",
            work_dir / f"{tex_file.stem}.css",
        )
        if not generated_html.is_file():
            raise ConversionError(
                f"make4ht did not create the expected file: {output_dir / f'{tex_file.stem}.html'}"
            )

        html = generated_html.read_text(encoding="utf-8")
        html = ensure_document_title(html)
        html = normalize_heading_levels(html)
        html = add_document_landmarks(html)
        html = make_mathml_explicit(html)
        html = mark_equation_layout_tables(html)
        html = improve_data_table_accessibility(html)
        html = repair_mathml_fidelity(html)
        if generated_css.is_file():
            css = generated_css.read_text(encoding="utf-8")
            html = inline_css(html, css, tex_file.stem)
            generated_css.unlink()
        else:
            html = rewrite_css_link(html, tex_file.stem, output_file.stem)
        math_errors = validate_mathml_structure(html)
        if math_errors:
            (make4ht_dir / "postprocessed.invalid.html").write_text(
                html, encoding="utf-8", newline="\n"
            )
            raise ConversionError(
                "The MathML structure is invalid:\n" + "\n".join(math_errors[:20])
            )
        output_file.write_text(html, encoding="utf-8", newline="\n")

        if keep_logs:
            save_conversion_logs(make4ht_dir, output_file)
        if keep_temporary_files:
            save_temporary_files(build_dir, output_file)
        return output_file
    except Exception as error:
        details = str(error)
        if keep_logs and make4ht_dir.is_dir():
            try:
                saved_logs = save_conversion_logs(make4ht_dir, output_file)
                details += f"\n\nDiagnostics saved to: {saved_logs}"
            except OSError as log_error:
                keep_build = True
                details += (
                    f"\nCould not copy logs: {log_error}. Build directory: {build_dir}"
                )
        if keep_temporary_files and build_dir.is_dir():
            try:
                saved_temporary = save_temporary_files(build_dir, output_file)
                details += f"\n\nTemporary files saved to: {saved_temporary}"
            except OSError as temporary_error:
                keep_build = True
                details += f"\nCould not copy temporary files: {temporary_error}. Build directory: {build_dir}"
        raise ConversionError(details) from error
    finally:
        if owns_build_dir and not keep_build:
            shutil.rmtree(build_dir, ignore_errors=True)


def first_existing(*paths: Path) -> Path:
    """Return the first existing path or the first candidate when none exists."""
    for path in paths:
        if path.exists():
            return path
    return paths[0]

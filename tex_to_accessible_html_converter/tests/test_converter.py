from pathlib import Path
from subprocess import CompletedProcess
import re

import pytest

import converter
from converter import (
    ConversionError,
    add_document_landmarks,
    configure_tex_environment,
    convert_tex_to_accessible_html,
    ensure_document_title,
    find_make4ht,
    first_existing,
    improve_data_table_accessibility,
    inline_css,
    is_miktex_path,
    make_mathml_explicit,
    mark_equation_layout_tables,
    normalize_heading_levels,
    output_file_for,
    rewrite_css_link,
    safe_temp_prefix,
)


@pytest.fixture(autouse=True)
def isolate_external_latex_validation(monkeypatch):
    """Pipeline unit tests replace native compilation, tested independently."""
    monkeypatch.setattr(converter, "validate_latex_document", lambda *args, **kwargs: [])


def without_formula_report(html):
    return re.sub(r'<script type="application/json" id="tex-formula-verification">.*?</script>\n?', '', html)


def test_heading_levels_are_compressed_without_changing_hierarchy():
    html = "<h1>Title</h1><h3>Section</h3><h4>Subsection</h4>"

    assert normalize_heading_levels(html) == (
        "<h1>Title</h1><h2>Section</h2><h3>Subsection</h3>"
    )


def test_document_title_uses_visible_h1_text():
    html = "<html><head><title></title></head><body><h1>Курс<br>математики</h1></body></html>"

    assert "<title>Курс математики</title>" in ensure_document_title(html)


def test_make_mathml_explicit_adds_namespace_to_math_tags():
    html = "<p><math display='inline'><mi>x</mi></math></p>"

    result = make_mathml_explicit(html)

    assert (
        "<math xmlns='http://www.w3.org/1998/Math/MathML' display='inline'>" in result
    )


def test_document_content_and_toc_get_landmarks():
    html = (
        "<html><head><title>Document</title></head><body>"
        "<h2 class='likechapterHead' id='contents'>Contents</h2>"
        "<div class='tableofcontents'><a href='#one'>One</a></div>"
        "<h2 id='one'>One</h2><p>Text</p>"
        "</body></html>"
    )

    result = add_document_landmarks(html)

    assert result.count("<main>") == 1
    assert result.count("</main>") == 1
    assert '<nav aria-label="Оглавление">' in result
    assert (
        '<nav aria-label="Оглавление">'
        "<h2 class='likechapterHead' id='contents'>Contents</h2>"
        "<div class='tableofcontents'><a href='#one'>One</a></div>"
        "</nav>"
    ) in result
    assert result.index("<main>") < result.index("<nav ")
    assert result.index("</nav>") < result.index("</main>")
    assert "<head><main>" not in result
    assert add_document_landmarks(result) == result


def test_toc_navigation_does_not_capture_previous_title_container():
    from html_validation import validate_html_structure
    html = ('<html><body><div class="maketitle"><h1>Book title</h1>'
            '<div class="author">Author</div></div>'
            '<h1>Contents</h1><div class="tableofcontents">Links</div>'
            '<h1>Chapter</h1></body></html>')
    result = add_document_landmarks(html)
    assert '<nav aria-label="Оглавление"><h1>Contents</h1>' in result
    assert result.index('Book title') < result.index('<nav ')
    assert validate_html_structure(result) == []


def test_document_without_toc_still_gets_main_landmark():
    html = "<html><head></head><body><p>Text</p></body></html>"

    result = add_document_landmarks(html)

    assert "<body>\n<main>\n<p>Text</p>\n</main>\n</body>" in result
    assert "<nav" not in result


def test_existing_main_landmark_is_preserved():
    html = "<html><body><main><p>Text</p></main></body></html>"

    assert add_document_landmarks(html) == html


def test_make_mathml_explicit_keeps_existing_namespace():
    html = '<math xmlns="http://www.w3.org/1998/Math/MathML"><mi>x</mi></math>'

    result = make_mathml_explicit(html)

    assert result == html


@pytest.mark.parametrize("class_name", ["equation", "equation-star"])
def test_equation_layout_tables_are_presentational(class_name):
    html = (
        f'<table class="{class_name}"><tr><td><math><mi>x</mi></math></td></tr></table>'
    )

    result = mark_equation_layout_tables(html)

    assert f"<table class=\"{class_name}\" role='presentation'>" in result
    assert "<math><mi>x</mi></math>" in result


def test_data_tables_are_not_marked_as_presentational():
    html = (
        "<table class='tabular'><tr><th>Variable</th></tr></table>"
        "<table><tr><td>Layout not known to be an equation</td></tr></table>"
    )

    assert mark_equation_layout_tables(html) == html


def test_existing_equation_table_role_is_preserved():
    html = "<table class='equation' role='math'><tr><td>x</td></tr></table>"

    assert mark_equation_layout_tables(html) == html


def test_captioned_data_table_gets_caption_relationship_and_headers():
    html = (
        "<figure id='table-figure'>"
        "<figcaption class='caption'>Values</figcaption>"
        "<div class='tabular'><table class='tabular' id='TBL-1'>"
        "<tr class='array-hline'><td></td><td></td></tr>"
        "<tr><td>Variable</td><td>Value</td></tr>"
        "<tr><td>x</td><td>1</td></tr>"
        "</table></div></figure>"
    )

    result = improve_data_table_accessibility(html)

    assert "<figcaption class='caption' id='TBL-1-caption'>" in result
    assert (
        "<table class='tabular' id='TBL-1' aria-labelledby='TBL-1-caption'>" in result
    )
    assert "<tr class='array-hline' aria-hidden='true'>" in result
    assert "<th scope='col'>Variable</th><th scope='col'>Value</th>" in result
    assert "<th scope='row'>x</th><td>1</td>" in result
    assert improve_data_table_accessibility(result) == result


def test_existing_caption_id_is_used_for_data_table():
    html = (
        "<figure><figcaption id='caption-1'>Values</figcaption>"
        "<table class='tabular' id='TBL-1'>"
        "<tr><td>Variable</td><td>Value</td></tr>"
        "</table></figure>"
    )

    result = improve_data_table_accessibility(html)

    assert "aria-labelledby='caption-1'" in result
    assert result.count("id='caption-1'") == 1


def test_equation_layout_table_does_not_get_data_headers():
    html = "<table class='equation'><tr><td><math><mi>x</mi></math></td></tr></table>"

    assert improve_data_table_accessibility(html) == html


def test_rewrite_css_link_updates_single_and_double_quoted_links():
    html = """<link href='source.css' /><link href="source.css" />"""

    result = rewrite_css_link(html, "source", "target")

    assert "href='target.css'" in result
    assert 'href="target.css"' in result


def test_inline_css_replaces_tex4ht_stylesheet_link():
    html = "<head><link href='source.css' rel='stylesheet' type='text/css' /></head>"

    result = inline_css(html, "body { color: black; }", "source")

    assert "<style>\nbody { color: black; }\n</style>" in result
    assert "source.css" not in result


def test_inline_css_supports_double_quoted_tex4ht_link():
    html = '<head><link href="source.css" rel="stylesheet" type="text/css" /></head>'

    result = inline_css(html, "body { color: black; }", "source")

    assert "<style>\nbody { color: black; }\n</style>" in result
    assert "source.css" not in result


def test_inline_css_falls_back_to_head_when_link_is_missing():
    html = "<html><head><title>Document</title></head><body></body></html>"

    result = inline_css(html, "body { color: black; }", "source")

    assert "<style>\nbody { color: black; }\n</style>\n</head>" in result


def test_output_file_for_uses_tex_folder_by_default():
    result = output_file_for(Path("C:/docs/source.tex"))

    assert result == Path("C:/docs/source.html")


def test_output_file_for_uses_selected_output_folder():
    result = output_file_for(Path("C:/docs/source.tex"), Path("D:/html"))

    assert result == Path("D:/html/source.html")


def test_safe_temp_prefix_uses_only_ascii_characters():
    result = safe_temp_prefix("Лекция 13_последняя")

    assert result == "13_-build-"
    assert result.encode("ascii")


def test_first_existing_returns_first_existing_path(tmp_path):
    missing = tmp_path / "missing.html"
    existing = tmp_path / "existing.html"
    existing.write_text("html", encoding="utf-8")

    result = first_existing(missing, existing)

    assert result == existing


def test_first_existing_returns_first_candidate_when_none_exist(tmp_path):
    first = tmp_path / "first.html"
    second = tmp_path / "second.html"

    result = first_existing(first, second)

    assert result == first


def test_is_miktex_path_detects_miktex_executable():
    assert is_miktex_path(r"C:\Program Files\MiKTeX\miktex\bin\x64\make4ht.exe")
    assert not is_miktex_path(r"C:\texlive\2025\bin\windows\make4ht.exe")


def test_find_make4ht_finds_miktex_candidate(monkeypatch, tmp_path):
    miktex_bin = tmp_path / "Programs" / "MiKTeX" / "miktex" / "bin" / "x64"
    miktex_bin.mkdir(parents=True)
    make4ht = miktex_bin / "make4ht.exe"
    make4ht.write_text("", encoding="utf-8")

    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setattr(converter.shutil, "which", lambda _name: None)

    assert find_make4ht("miktex") == str(make4ht)


def test_find_make4ht_prefers_path_in_auto_mode(monkeypatch):
    monkeypatch.setattr(
        converter.shutil,
        "which",
        lambda _name: r"C:\texlive\2025\bin\windows\make4ht.exe",
    )
    monkeypatch.setattr(converter, "miktex_bin_candidates", list)

    assert find_make4ht("auto") == r"C:\texlive\2025\bin\windows\make4ht.exe"


def test_find_make4ht_requires_miktex_for_miktex_mode(monkeypatch):
    monkeypatch.setattr(
        converter.shutil,
        "which",
        lambda _name: r"C:\texlive\2025\bin\windows\make4ht.exe",
    )
    monkeypatch.setattr(converter, "miktex_bin_candidates", list)

    assert find_make4ht("miktex") is None


def test_find_make4ht_skips_miktex_before_texlive_in_path(monkeypatch, tmp_path):
    miktex = tmp_path / "MiKTeX" / "bin"
    texlive = tmp_path / "texlive" / "bin"
    for directory in (miktex, texlive):
        directory.mkdir(parents=True)
        (directory / "make4ht.exe").touch()
    monkeypatch.setattr(
        converter.shutil, "which", lambda name: str(miktex / "make4ht.exe")
    )
    monkeypatch.setattr(
        converter.os, "get_exec_path", lambda: [str(miktex), str(texlive)]
    )

    assert find_make4ht("texlive") == str(texlive / "make4ht.exe")


def test_run_make4ht_uses_selected_distribution_for_child_processes(
    monkeypatch, tmp_path
):
    executable = tmp_path / "texlive" / "bin" / "make4ht.exe"
    (tmp_path / "source.tex").write_text(
        r"\documentclass{article}\begin{document}x\end{document}", encoding="utf-8"
    )
    monkeypatch.setattr(converter, "find_make4ht", lambda distribution: str(executable))
    monkeypatch.setenv("PATH", "other-distribution")
    captured = {}

    def fake_run(command, **kwargs):
        captured.update(kwargs)
        assert command[0] == str(executable)
        assert "\\" not in command[command.index("-c") + 1]
        return CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(converter, "run_logged_process", fake_run)
    converter.run_make4ht(
        tmp_path / "source.tex", tmp_path, tmp_path, "lualatex", "texlive"
    )

    assert (
        captured["env"]["PATH"]
        == str(executable.parent) + converter.os.pathsep + "other-distribution"
    )


def test_find_make4ht_does_not_substitute_another_distribution(monkeypatch, tmp_path):
    monkeypatch.setattr(
        converter.shutil, "which", lambda name: r"C:\MiKTeX\bin\make4ht.exe"
    )
    monkeypatch.setattr(converter.os, "get_exec_path", list)
    monkeypatch.setenv("SystemDrive", str(tmp_path))
    assert find_make4ht("texlive") is None


def test_run_make4ht_reports_missing_texlive(monkeypatch, tmp_path):
    monkeypatch.setattr(converter, "find_make4ht", lambda distribution: None)
    with pytest.raises(ConversionError, match="TeX Live make4ht was not found"):
        converter.run_make4ht(
            tmp_path / "source.tex",
            tmp_path,
            tmp_path,
            "lualatex",
            "texlive",
        )


def test_conversion_uses_complete_passes_for_accessible_output(monkeypatch, tmp_path):
    source = tmp_path / "source.tex"
    source.write_text(r"\documentclass{article}", encoding="utf-8")
    executable = tmp_path / "texlive" / "bin" / "make4ht.exe"
    captured = {}

    monkeypatch.setattr(
        converter, "find_make4ht", lambda _distribution: str(executable)
    )

    def fake_run(command, **kwargs):
        captured["command"] = command
        return CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(converter, "run_logged_process", fake_run)

    converter.run_make4ht(source, tmp_path, tmp_path, "latex", "texlive")

    command = captured["command"]
    assert command[command.index("-m") + 1] == "default"


def test_configure_tex_environment_preserves_miktex_roots(tmp_path):
    env = {
        "MIKTEX_USERCONFIG": "existing-config",
        "MIKTEX_USERDATA": "existing-data",
        "MIKTEX_USERINSTALL": "existing-packages",
    }

    configure_tex_environment(env, tmp_path, "miktex")

    assert "TEXMFVAR" not in env
    assert "TEXMFCACHE" not in env
    assert env["MIKTEX_USERCONFIG"] == "existing-config"
    assert env["MIKTEX_USERDATA"] == "existing-data"
    assert env["MIKTEX_USERINSTALL"] == "existing-packages"


def test_miktex_preserves_configured_font_caches(tmp_path):
    env = {
        "TEXMFVAR": "existing-var",
        "TEXMFCONFIG": "existing-config",
        "TEXMFCACHE": "existing-cache",
    }
    previous = env.copy()
    configure_tex_environment(env, tmp_path, "miktex")
    assert env == previous
    assert not list(tmp_path.iterdir())


def test_texlive_preserves_configured_font_caches(tmp_path):
    env = {
        "TEXMFVAR": "existing-var",
        "TEXMFCONFIG": "existing-config",
        "TEXMFCACHE": "existing-cache",
    }
    previous = env.copy()

    configure_tex_environment(env, tmp_path, "texlive")

    assert env == previous
    assert not list(tmp_path.iterdir())


def test_convert_tex_to_accessible_html_inlines_css_and_removes_css(
    monkeypatch, tmp_path
):
    tex_file = tmp_path / "source.tex"
    tex_file.write_text(r"\documentclass{article}", encoding="utf-8")
    output_file = tmp_path / "result.html"

    def fake_run_make4ht(
        tex_file, output_dir, build_dir, engine, tex_distribution="auto", **kwargs
    ):
        (output_dir / "source.html").write_text(
            "<html><head><title></title><link href='source.css' rel='stylesheet' /></head>"
            "<body><h2>Курс математики</h2><math><mi>x</mi></math></body></html>",
            encoding="utf-8",
        )
        (output_dir / "source.css").write_text(
            "body { color: black; }", encoding="utf-8"
        )
        return CompletedProcess(args=[], returncode=0, stdout="", stderr="")

    monkeypatch.setattr(converter, "run_make4ht", fake_run_make4ht)

    result = convert_tex_to_accessible_html(
        tex_file, output_file=output_file, engine="lualatex"
    )

    assert result == output_file.resolve()
    html = output_file.read_text(encoding="utf-8")
    assert "<style>\nbody { color: black; }\n</style>" in html
    assert "<title>Курс математики</title>" in html
    assert "<h1>Курс математики</h1>" in html
    assert "<math xmlns='http://www.w3.org/1998/Math/MathML'>" in html
    assert not (tmp_path / "source.css").exists()


def test_convert_tex_to_accessible_html_runs_make4ht_inside_build_dir(
    monkeypatch, tmp_path
):
    tex_file = tmp_path / "source.tex"
    tex_file.write_text(r"\documentclass{article}", encoding="utf-8")
    output_dir = tmp_path / "chosen"
    seen_output_dirs = []

    def fake_run_make4ht(
        tex_file, output_dir, build_dir, engine, tex_distribution="auto", **kwargs
    ):
        seen_output_dirs.append(output_dir)
        (build_dir / "source.html").write_text(
            "<html><head></head><body>ok</body></html>", encoding="utf-8"
        )
        return CompletedProcess(args=[], returncode=0, stdout="", stderr="")

    monkeypatch.setattr(converter, "run_make4ht", fake_run_make4ht)

    result = convert_tex_to_accessible_html(
        tex_file, output_file=output_dir / "source.html"
    )

    assert result == (output_dir / "source.html").resolve()
    assert seen_output_dirs[0] != output_dir.resolve()
    assert without_formula_report(result.read_text(encoding="utf-8")) == (
        "<html><head></head><body>\n<main>\nok\n</main>\n</body></html>"
    )


def test_convert_tex_to_accessible_html_stages_source_tree_before_make4ht(
    monkeypatch, tmp_path
):
    source_dir = tmp_path / "математика" / "лекция"
    source_dir.mkdir(parents=True)
    tex_file = source_dir / "source.tex"
    tex_file.write_text(
        "\\cfrac{1}{2}\\input{chapter.tex}\n\\begin{multline}\na+b=\\\\\nc+d\n\\end{multline}",
        encoding="utf-8",
    )
    (source_dir / "chapter.tex").write_text(r"chapter \cfrac {3}{4}", encoding="utf-8")
    (source_dir / "source.html").write_text("stale html", encoding="utf-8")
    (source_dir / "source.css").write_text("stale css", encoding="utf-8")
    output_file = source_dir / "result.html"
    build_root = tmp_path / "ascii-build"
    seen_tex_files = []

    def fake_run_make4ht(
        tex_file, output_dir, build_dir, engine, tex_distribution="auto", **kwargs
    ):
        seen_tex_files.append(tex_file)
        assert tex_file.parent != source_dir.resolve()
        assert tex_file.read_text(encoding="utf-8") == (
            "\\cfrac{1}{2}\\input{chapter.tex}\n"
            "\\begin{multline}\n"
            "a+b=\\\\\n"
            "c+d\n"
            "\\end{multline}"
        )
        assert (tex_file.parent / "chapter.tex").read_text(
            encoding="utf-8"
        ) == r"chapter \cfrac {3}{4}"
        assert not (tex_file.parent / "source.html").exists()
        assert not (tex_file.parent / "source.css").exists()
        (build_dir / "source.html").write_text(
            "<html><head></head><body>fresh</body></html>", encoding="utf-8"
        )
        return CompletedProcess(args=[], returncode=0, stdout="", stderr="")

    monkeypatch.setattr(converter, "run_make4ht", fake_run_make4ht)

    result = convert_tex_to_accessible_html(
        tex_file, output_file=output_file, build_dir=build_root
    )

    assert seen_tex_files == [build_root.resolve() / "source" / "source.tex"]
    assert without_formula_report(result.read_text(encoding="utf-8")) == (
        "<html><head></head><body>\n<main>\nfresh\n</main>\n</body></html>"
    )
    assert "\\cfrac{1}{2}" in tex_file.read_text(encoding="utf-8")


def test_conversion_keeps_original_tex_bytes_unchanged(monkeypatch, tmp_path):
    source = tmp_path / "source.tex"
    original = b"% exact bytes\r\n\\verb|\\cfrac|\r\n\\begin{document}\r\ntext\r\n\\end{document}\r\n"
    source.write_bytes(original)

    def fake_run(tex_file, output_dir, build_dir, *args, **kwargs):
        assert tex_file.read_bytes() == original
        (build_dir / "source.html").write_text(
            "<html><head></head><body>text</body></html>", encoding="utf-8"
        )
        return CompletedProcess([], 0, "", "")

    monkeypatch.setattr(converter, "run_make4ht", fake_run)

    convert_tex_to_accessible_html(source, engine="xelatex", tex_distribution="miktex")

    assert source.read_bytes() == original


def test_run_make4ht_adds_miktex_and_xetex_compatibility_to_staged_copy(
    monkeypatch, tmp_path
):
    source = tmp_path / "source.tex"
    original = "\\documentclass{article}\n\\begin{document}x\\end{document}\n"
    source.write_text(original, encoding="utf-8", newline="\n")
    executable = tmp_path / "MiKTeX" / "bin" / "make4ht.exe"

    monkeypatch.setattr(
        converter, "find_make4ht", lambda _distribution: str(executable)
    )

    def fake_process(command, **kwargs):
        staged = source.read_text(encoding="utf-8")
        assert staged.startswith(
            converter.XETEX_CYRILLIC_COMPAT
            + "\n"
            + converter.MIKTEX_PARAGRAPH_COMPAT
            + "\n"
        )
        assert staged.endswith(original)
        return CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(converter, "run_logged_process", fake_process)

    converter.run_make4ht(source, tmp_path, tmp_path, "xelatex", "miktex")


def test_run_make4ht_applies_confirmed_staged_compatibility_for_classic_texlive_latex(
    monkeypatch, tmp_path
):
    source = tmp_path / "source.tex"
    source.write_text(
        "\\begin{document}$D=-36<0$\\begin{equation}\\begin{gathered}"
        "\\cfrac{1}{2}\\end{gathered}\\end{equation}\\end{document}",
        encoding="utf-8",
    )
    executable = tmp_path / "texlive" / "bin" / "make4ht.exe"
    monkeypatch.setattr(
        converter, "find_make4ht", lambda _distribution: str(executable)
    )

    def fake_process(command, **kwargs):
        staged = source.read_text(encoding="utf-8")
        assert '$D=-36\\mathchar"313C 0$' in staged
        assert "\\begin{gathered}" in staged
        assert "\\dfrac{1}{2}" in staged
        assert "\\cfrac" not in staged
        return CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(converter, "run_logged_process", fake_process)

    converter.run_make4ht(source, tmp_path, tmp_path, "latex", "texlive")


def test_source_repairs_only_modify_staged_copy_and_are_logged(monkeypatch, tmp_path):
    source_dir = tmp_path / "original"
    source_dir.mkdir()
    original = source_dir / "source.tex"
    original_bytes = r'$a \), \( b$ {\itПример}'.encode("utf-8")
    original.write_bytes(original_bytes)
    build_dir = tmp_path / "build"
    build_dir.mkdir()
    staged = converter.stage_source_tree(original, build_dir / "source", build_dir)
    monkeypatch.setattr(converter, "find_make4ht", lambda _: "texlive/bin/make4ht")

    def fake_process(command, **kwargs):
        assert staged.read_text(encoding="utf-8") == r'$a $, $ b$ {\it Пример}'
        assert original.read_bytes() == original_bytes
        return CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(converter, "run_logged_process", fake_process)
    converter.run_make4ht(staged, build_dir, build_dir, "latex", "texlive")
    assert (build_dir / "source.original.tex").read_bytes() == original_bytes
    assert (build_dir / "source.corrected.tex").read_text(encoding="utf-8") == r'$a $, $ b$ {\it Пример}'
    saved = converter.save_conversion_logs(build_dir, tmp_path / "output.html")
    report = (saved / "source-repairs.txt").read_text(encoding="utf-8")
    assert "mixed inline math delimiters" in report
    assert "italic command" in report
    assert original.read_bytes() == original_bytes


def test_convert_tex_to_accessible_html_prefers_fresh_build_dir_output(
    monkeypatch, tmp_path
):
    tex_file = tmp_path / "source.tex"
    tex_file.write_text(r"\documentclass{article}", encoding="utf-8")
    output_dir = tmp_path / "html"
    output_dir.mkdir()
    stale_output = output_dir / "source.html"
    stale_output.write_text(
        "<html><head><style>old</style></head><body>old</body></html>", encoding="utf-8"
    )

    def fake_run_make4ht(
        tex_file, output_dir, build_dir, engine, tex_distribution="auto", **kwargs
    ):
        (build_dir / "source.html").write_text(
            "<html><head><link href='source.css' rel='stylesheet' /></head><body>fresh</body></html>",
            encoding="utf-8",
        )
        (build_dir / "source.css").write_text(
            "body { color: fresh; }", encoding="utf-8"
        )
        return CompletedProcess(args=[], returncode=0, stdout="", stderr="")

    monkeypatch.setattr(converter, "run_make4ht", fake_run_make4ht)

    output_file = convert_tex_to_accessible_html(
        tex_file, output_file=output_dir / "source.html"
    )

    html = output_file.read_text(encoding="utf-8")
    assert "fresh" in html
    assert "old" not in html
    assert html.count("<style>") == 1


def test_convert_tex_to_accessible_html_rewrites_css_link_when_css_is_missing(
    monkeypatch, tmp_path
):
    tex_file = tmp_path / "source.tex"
    tex_file.write_text(r"\documentclass{article}", encoding="utf-8")

    def fake_run_make4ht(
        tex_file, output_dir, build_dir, engine, tex_distribution="auto", **kwargs
    ):
        (output_dir / "source.html").write_text(
            '<html><head><link href="source.css" rel="stylesheet" /></head></html>',
            encoding="utf-8",
        )
        return CompletedProcess(args=[], returncode=0, stdout="", stderr="")

    monkeypatch.setattr(converter, "run_make4ht", fake_run_make4ht)

    output_file = convert_tex_to_accessible_html(
        tex_file, output_file=tmp_path / "renamed.html"
    )

    assert 'href="renamed.css"' in output_file.read_text(encoding="utf-8")


def test_convert_tex_to_accessible_html_raises_for_missing_input(tmp_path):
    with pytest.raises(ConversionError, match="source file does not exist"):
        convert_tex_to_accessible_html(tmp_path / "missing.tex")


def test_convert_tex_to_accessible_html_raises_when_make4ht_fails(
    monkeypatch, tmp_path
):
    tex_file = tmp_path / "source.tex"
    tex_file.write_text(r"\documentclass{article}", encoding="utf-8")

    def fake_run_make4ht(
        tex_file, output_dir, build_dir, engine, tex_distribution="auto", **kwargs
    ):
        return CompletedProcess(args=[], returncode=1, stdout="out", stderr="err")

    monkeypatch.setattr(converter, "run_make4ht", fake_run_make4ht)

    with pytest.raises(ConversionError, match="make4ht failed"):
        convert_tex_to_accessible_html(tex_file)


def test_convert_tex_to_accessible_html_cleans_temporary_build_dir(
    monkeypatch, tmp_path
):
    tex_file = tmp_path / "source.tex"
    tex_file.write_text(r"\documentclass{article}", encoding="utf-8")
    seen_build_dirs = []

    def fake_run_make4ht(
        tex_file, output_dir, build_dir, engine, tex_distribution="auto", **kwargs
    ):
        seen_build_dirs.append(build_dir)
        (build_dir / "source.html").write_text(
            "<html><head></head></html>", encoding="utf-8"
        )
        return CompletedProcess(args=[], returncode=0, stdout="", stderr="")

    monkeypatch.setattr(converter, "run_make4ht", fake_run_make4ht)

    convert_tex_to_accessible_html(tex_file)

    assert seen_build_dirs
    assert not seen_build_dirs[0].exists()


def test_tex_errors_preserve_diagnostics_and_existing_output(monkeypatch, tmp_path):
    source = tmp_path / "source.tex"
    source.write_text("test", encoding="utf-8")
    output = source.with_suffix(".html")
    output.write_text("previous result", encoding="utf-8")
    builds = []

    def fake_run(tex_file, output_dir, build_dir, *args, **kwargs):
        builds.append(build_dir)
        (build_dir / "source.html").write_text("broken result", encoding="utf-8")
        (build_dir / "source.log").write_text(
            "! Undefined control sequence.\nl.5 \\bad\n", encoding="utf-8"
        )
        return CompletedProcess([], 0, "stdout evidence", "stderr evidence")

    monkeypatch.setattr(converter, "run_make4ht", fake_run)
    with pytest.raises(ConversionError, match="Undefined control sequence") as error:
        convert_tex_to_accessible_html(source, keep_logs=True)
    assert "Diagnostics saved" in str(error.value)
    assert output.read_text(encoding="utf-8") == "previous result"
    saved = next(converter.logs_directory_for(output).iterdir())
    assert (saved / "stdout.txt").read_text(encoding="utf-8") == "stdout evidence"
    assert (saved / "stderr.txt").read_text(encoding="utf-8") == "stderr evidence"
    assert not builds[0].exists()


def test_broken_mathml_does_not_replace_previous_html(monkeypatch, tmp_path):
    source = tmp_path / "source.tex"
    source.write_text("test", encoding="utf-8")
    output = source.with_suffix(".html")
    output.write_text("previous", encoding="utf-8")

    def fake_run(tex_file, output_dir, build_dir, *args, **kwargs):
        (build_dir / "source.html").write_text(
            "<math><mrow><mi>x</mi></math>", encoding="utf-8"
        )
        return CompletedProcess([], 0, "", "")

    monkeypatch.setattr(converter, "run_make4ht", fake_run)
    with pytest.raises(ConversionError, match="MathML structure is invalid"):
        convert_tex_to_accessible_html(source)
    assert output.read_text(encoding="utf-8") == "previous"


@pytest.mark.parametrize("timeout", [0, -1, float("inf"), float("nan")])
def test_invalid_timeout_is_rejected(tmp_path, timeout):
    with pytest.raises(ConversionError, match="timeout"):
        convert_tex_to_accessible_html(tmp_path / "source.tex", timeout=timeout)


def test_output_cannot_overwrite_source(tmp_path):
    source = tmp_path / "source.tex"
    source.write_bytes(b"original")
    with pytest.raises(ConversionError, match="must differ"):
        convert_tex_to_accessible_html(source, output_file=source)
    assert source.read_bytes() == b"original"


def test_html_errors_preserve_previous_output(monkeypatch, tmp_path):
    source = tmp_path / "source.tex"
    source.write_text("text", encoding="utf-8")
    output = source.with_suffix(".html")
    output.write_bytes(b"previous")

    def fake_run(tex_file, output_dir, build_dir, *args, **kwargs):
        (build_dir / "source.html").write_text(
            '<html><body><div><span>broken</div></span></body></html>',
            encoding="utf-8",
        )
        return CompletedProcess([], 0, "", "")

    monkeypatch.setattr(converter, "run_make4ht", fake_run)
    with pytest.raises(ConversionError, match="HTML structure is invalid"):
        convert_tex_to_accessible_html(source)
    assert output.read_bytes() == b"previous"


def test_broken_link_does_not_replace_previous_html(monkeypatch, tmp_path):
    source = tmp_path / "source.tex"
    source.write_text("text", encoding="utf-8")
    output = tmp_path / "renamed.html"
    output.write_bytes(b"previous")

    def fake_run(tex_file, output_dir, build_dir, *args, **kwargs):
        (build_dir / "source.html").write_text(
            '<html><body><a href="#missing">Reference</a></body></html>', encoding="utf-8"
        )
        return CompletedProcess([], 0, "", "")

    monkeypatch.setattr(converter, "run_make4ht", fake_run)
    with pytest.raises(ConversionError, match="Link verification failed"):
        convert_tex_to_accessible_html(source, output_file=output)
    assert output.read_bytes() == b"previous"


def test_output_rename_keeps_self_reference_destination(monkeypatch, tmp_path):
    source = tmp_path / "source.tex"
    source.write_text("text", encoding="utf-8")

    def fake_run(tex_file, output_dir, build_dir, *args, **kwargs):
        (build_dir / "source.html").write_text(
            '<html><body><i id="eq1"></i><a href="source.html#eq1">Equation</a></body></html>', encoding="utf-8"
        )
        return CompletedProcess([], 0, "", "")

    monkeypatch.setattr(converter, "run_make4ht", fake_run)
    result = convert_tex_to_accessible_html(source, output_file=tmp_path / "renamed.html")
    assert 'href="#eq1"' in result.read_text(encoding="utf-8")


def test_failed_publication_preserves_output_and_removes_pending(monkeypatch, tmp_path):
    source = tmp_path / "verified.html"
    source.write_bytes(b"new")
    output = tmp_path / "result.html"
    output.write_bytes(b"previous")

    def fail_replace(*args):
        raise PermissionError("locked destination")

    monkeypatch.setattr(converter.os, "replace", fail_replace)
    with pytest.raises(PermissionError):
        converter.publish_verified_html(source, output)
    assert output.read_bytes() == b"previous"
    assert not list(tmp_path.glob(".tex-html-*.tmp"))


def test_reused_build_does_not_publish_stale_html(monkeypatch, tmp_path):
    source_dir = tmp_path / "input"
    source_dir.mkdir()
    source = source_dir / "source.tex"
    source.write_text("text", encoding="utf-8")
    build = tmp_path / "build"
    (build / "make4ht").mkdir(parents=True)
    (build / "make4ht/source.html").write_text("stale", encoding="utf-8")
    monkeypatch.setattr(converter, "run_make4ht", lambda *a, **k: CompletedProcess([], 0, "", ""))
    with pytest.raises(ConversionError, match="did not create"):
        convert_tex_to_accessible_html(source, build_dir=build)
    assert not source.with_suffix(".html").exists()


@pytest.mark.parametrize("keep_logs", [False, True])
@pytest.mark.parametrize("failed", [False, True])
def test_log_option_controls_retention_on_success_and_failure(
    monkeypatch, tmp_path, keep_logs, failed
):
    source = tmp_path / "source.tex"
    source.write_text("test", encoding="utf-8")
    builds = []

    def fake_run(tex_file, output_dir, build_dir, *args, **kwargs):
        builds.append(build_dir)
        (build_dir / "source.html").write_text("<html>ok</html>", encoding="utf-8")
        (build_dir / "source.log").write_text("TeX log", encoding="utf-8")
        return CompletedProcess([], int(failed), "stdout", "stderr")

    monkeypatch.setattr(converter, "run_make4ht", fake_run)
    if failed:
        with pytest.raises(ConversionError) as error:
            convert_tex_to_accessible_html(source, keep_logs=keep_logs)
        assert ("Diagnostics saved" in str(error.value)) == keep_logs
    else:
        convert_tex_to_accessible_html(source, keep_logs=keep_logs)
    assert not builds[0].exists()
    logs = converter.logs_directory_for(source.with_suffix(".html"))
    assert logs.exists() == keep_logs
    if keep_logs:
        assert next(logs.glob("*/source.log")).read_text(encoding="utf-8") == "TeX log"


@pytest.mark.parametrize("failed", [False, True])
def test_temporary_option_preserves_complete_build_tree(monkeypatch, tmp_path, failed):
    source = tmp_path / "source.tex"
    source.write_text("test", encoding="utf-8")

    def fake_run(tex_file, output_dir, build_dir, *args, **kwargs):
        (build_dir / "source.html").write_text("<html>ok</html>", encoding="utf-8")
        (build_dir / "nested").mkdir()
        (build_dir / "nested" / "intermediate.tmp").write_text(
            "evidence", encoding="utf-8"
        )
        return CompletedProcess([], int(failed), "stdout", "stderr")

    monkeypatch.setattr(converter, "run_make4ht", fake_run)
    if failed:
        with pytest.raises(ConversionError, match="Temporary files saved"):
            convert_tex_to_accessible_html(source, keep_temporary_files=True)
    else:
        convert_tex_to_accessible_html(source, keep_temporary_files=True)

    temporary = converter.temporary_directory_for(source.with_suffix(".html"))
    assert (
        next(temporary.rglob("intermediate.tmp")).read_text(encoding="utf-8")
        == "evidence"
    )

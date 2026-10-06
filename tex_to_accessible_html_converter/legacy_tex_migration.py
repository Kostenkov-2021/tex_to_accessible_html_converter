"""Modernize documented LaTeX 2.09 font switches in staged text groups only.

Reference: https://www.latex-project.org/help/documentation/fntguide.pdf
The normalfont reset is essential: old switches reset other font attributes.
"""

from bisect import bisect_right
import re


SWITCHES = {"it": "itshape", "bf": "bfseries", "rm": "rmfamily", "sf": "sffamily",
            "tt": "ttfamily", "sl": "slshape", "sc": "scshape"}
TOKENS = re.compile(
    r"(?P<protected>%[^\n]*|\\verb\*?(?P<delimiter>[^\w\s]).*?(?P=delimiter)"
    r"|\\begin\{(?P<literal>verbatim\*?|lstlisting|minted)\}.*?\\end\{(?P=literal)\}"
    r"|\\[%\\$])"
    r"|(?P<math>\$\$?|\\[()[\]]|\\(?:begin|end)\{(?:math|displaymath|equation\*?|align\*?|alignat\*?|gather\*?|multline\*?|eqnarray\*?)\})"
    r"|(?P<legacy>\{[ \t]*\\(?P<name>it|bf|rm|sf|tt|sl|sc))(?![A-Za-z@])",
    re.DOTALL,
)


def modernize_legacy_text(source):
    """Return equivalent text declarations and an audit list; preserve math."""
    protected = re.compile(TOKENS.pattern.split(r"|(?P<math>")[0], re.DOTALL)
    masked = protected.sub(lambda m: " " * len(m[0]), source)
    document = re.search(r"\\begin\{document\}(.*?)\\end\{document\}", masked, re.DOTALL)
    if document is None:
        return source, []
    if re.search(r"\\documentclass(?:\[[^]]*\])?\{(?!article\}|report\}|book\})", masked[:document.start()]):
        return source, []
    body = source[document.start(1):document.end(1)]
    # Do not reinterpret a font command that the document explicitly overrides.
    if re.search(r"\\(?:def|gdef|edef|xdef|let|catcode|renewcommand|DeclareOldFontCommand)\b", masked):
        return source, []
    if re.search(r"\\(?:newcommand|providecommand|newenvironment|renewenvironment)\b", masked[document.start(1):document.end(1)]):
        return source, []
    end_math = None
    changes, parts, cursor = [], [], 0
    newlines = [m.start() for m in re.finditer("\n", source)]
    for match in TOKENS.finditer(body):
        if match.group("protected"):
            continue
        if match.group("math"):
            value = match[0]
            if end_math is None:
                if value in {"$", "$$", r"\(", r"\["}:
                    end_math = {r"\(": r"\)", r"\[": r"\]"}.get(value, value)
                elif value.startswith(r"\begin"):
                    end_math = value.replace(r"\begin", r"\end", 1)
            elif value == end_math:
                end_math = None
            continue
        if end_math is not None:
            continue
        name = match.group("name")
        modern = r"\normalfont" + "\\" + SWITCHES[name]
        replacement = match[0][:-len(name)-1] + modern + " "
        parts.extend([body[cursor:match.start()], replacement])
        cursor = match.end()
        changes.append({"line": bisect_right(newlines, document.start(1) + match.start()) + 1,
                        "old": "\\" + name, "new": modern})
    parts.append(body[cursor:])
    return source[:document.start(1)] + "".join(parts) + source[document.end(1):], changes

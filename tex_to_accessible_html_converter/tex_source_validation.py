"""Detect and repair confirmed source mistakes in staged TeX copies only.

Inline math uses paired delimiters: https://www.overleaf.com/learn/latex/Mathematical_expressions
This is a narrow compatibility check, not a general TeX parser.
"""

import re
from bisect import bisect_right


TOKENS = re.compile(
    r"(?P<protected>%[^\n]*|\\verb\*?(?P<delimiter>[^\w\s]).*?(?P=delimiter)"
    r"|\\begin\{(?P<literal>verbatim\*?|lstlisting|minted)\}.*?\\end\{(?P=literal)\}"
    r"|\\[%\\$]|\$\$.*?\$\$)"
    r"|(?P<mixed>\$(?!\$)(?:\\[^()\n]|[^$%\\\n])*"
    r"\\\)(?P<separator>[^$%\\\n]*)\\\("
    r"(?:\\[^()\n]|[^$%\\\n])*\$(?!\$))"
    r"|(?P<italic>\\it)(?P<word>[А-Яа-яЁё]+)",
    re.DOTALL,
)


def repair_tex_source(text: str) -> tuple[str, list[str]]:
    """Repair recognized source mistakes, preserving literal examples."""
    diagnostics = []
    newlines = [match.start() for match in re.finditer("\n", text)]

    def replace(match: re.Match[str]) -> str:
        if match.group("protected"):
            return match[0]
        line = bisect_right(newlines, match.start()) + 1
        if match.group("mixed"):
            diagnostics.append(f"Line {line}: repaired mixed inline math delimiters")
            return match[0].replace(r"\)", "$", 1).replace(r"\(", "$", 1)
        diagnostics.append(f"Line {line}: separated italic command from Cyrillic text")
        return r"\it " + match.group("word")

    corrected = TOKENS.sub(replace, text)
    # Loading arrows.meta in the document body exposes its definitions to
    # babel's active quotation mark. Move only a standalone, known command;
    # retain punctuation and comments at its original position.
    protected = [(m.start(), m.end()) for m in TOKENS.finditer(corrected) if m.group("protected")]
    visible = lambda position: not any(start <= position < end for start, end in protected)
    beginnings = [m for m in re.finditer(r"\\begin\{document\}", corrected) if visible(m.start())]
    if len(beginnings) == 1:
        beginning = beginnings[0]
        preamble = corrected[:beginning.start()]
        libraries = [m for m in re.finditer(r"(?m)^[ \t]*(\\usetikzlibrary\{arrows\.meta\})(?=[ \t]*(?:\.|%|$))", corrected) if m.start() > beginning.end() and visible(m.start())]
        if (len(libraries) == 1
                and any(visible(m.start()) for m in re.finditer(r"\\usepackage(?:\[[^\]]*\])?\{babel\}", preamble))
                and any(visible(m.start()) for m in re.finditer(r"\\usepackage(?:\[[^\]]*\])?\{tikz\}", preamble))):
            library = libraries[0]
            line = corrected.count("\n", 0, library.start()) + 1
            start, end = library.span(1)
            corrected = corrected[:start] + corrected[end:]
            corrected = corrected[:beginning.start()] + library.group(1) + "\n" + corrected[beginning.start():]
            diagnostics.append(f"Line {line}: moved arrows.meta loading into preamble for babel compatibility")
    return corrected, diagnostics


def validate_tex_source(text: str) -> list[str]:
    """Report any remaining mistakes covered by the staged source repair."""
    return repair_tex_source(text)[1]

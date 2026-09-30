"""Small source adaptations for TeX4ht, applied only to staged copies."""

import re


def isolate_unscripted_operators(text: str) -> str:
    """Prevent TeX4ht limit state leaking from an unscripted operator.

    Keep explicitly scripted operators unchanged, including explicit limit
    controls. Comments and verbatim material must not be interpreted as TeX.
    """
    pattern = re.compile(
        r"(?P<protected>%[^\n]*|\\verb\*?(?P<delimiter>[^\w\s]).*?(?P=delimiter)"
        r"|\\begin\{(?P<literal>verbatim\*?|lstlisting|minted)\}.*?\\end\{(?P=literal)\})"
        r"|(?P<escape>\\[%\\])"
        r"|(?P<operator>\\(?:sum|prod|coprod|bigcup|bigcap|det|lim|max|min|sup|inf))(?![A-Za-z])",
        re.DOTALL,
    )

    def replace(match):
        if not match.group("operator"):
            return match[0]
        remaining = match.string[match.end() :]
        whitespace = re.match(r"(?:\s|%[^\n]*(?:\n|$))*", remaining)
        assert whitespace is not None  # The pattern also matches an empty string.
        following = whitespace.end()
        if re.match(
            r"[_^]|\\(?:limits|nolimits|displaylimits)(?![A-Za-z])",
            remaining[following:],
        ):
            return match[0]
        if (
            match.start()
            and match.string[match.start() - 1] == "{"
            and remaining.startswith("}")
        ):
            return match[0]
        return "{" + match[0] + "}"

    delimiters = re.compile(
        r"%[^\n]*|\\verb\*?(?P<delim>[^\w\s]).*?(?P=delim)"
        r"|\\begin\{(?P<verbatim>verbatim\*?|lstlisting|minted)\}.*?\\end\{(?P=verbatim)\}"
        r"|\\[%\\$]|\$\$?|\\[\[\]()]"
        r"|\\(?:begin|end)\{(?:equation\*?|align\*?|gather\*?|multline\*?|displaymath|math|eqnarray\*?)\}",
        re.DOTALL,
    )
    end_token = None
    start = 0
    last = 0
    parts: list[str] = []
    for token in delimiters.finditer(text):
        value = token[0]
        if end_token is None:
            if value in ("$", "$$", r"\(", r"\["):
                end_token = {r"\(": r"\)", r"\[": r"\]"}.get(value, value)
            elif value.startswith(r"\begin{") and not token.group("verbatim"):
                end_token = value.replace(r"\begin", r"\end", 1)
            else:
                continue
            start = token.end()
        elif value == end_token:
            formula = text[start : token.start()]
            parts.extend((text[last:start], pattern.sub(replace, formula)))
            last = token.start()
            end_token = None
    parts.append(text[last:])
    return "".join(parts)


MIKTEX_PARAGRAPH_COMPAT = r"\ifdefined\partokencontext\partokencontext=0\relax\fi"
XETEX_CYRILLIC_COMPAT = (
    r"\ifdefined\xeuniregisterblockhex\xeuniregisterblockhex{0400}{052F}\fi"
)
LUATEX_UNICODE_FONT_COMPAT = (
    r"\usepackage{fontspec}"
    "\n"
    r"\IfFontExistsTF{Arial}{\setmainfont{Arial}}{\setmainfont{DejaVu Serif}}"
)

# Keep mathematical accents as operations, not precomposed alphabetic letters.
MATHML_CONFIG = r"""\Preamble{xhtml,mathml}
\Configure{accent}\hat\hat{{}{}}{}{\HCode{<mover accent="true"><mrow>}#2\HCode{</mrow><mo>\string&\#x005E;</mo></mover>}}
\Configure{accent}\bar\bar{{}{}}{}{\HCode{<mover accent="true"><mrow>}#2\HCode{</mrow><mo>\string&\#x00AF;</mo></mover>}}
\Configure{accent}\tilde\tilde{{}{}}{}{\HCode{<mover accent="true"><mrow>}#2\HCode{</mrow><mo>\string&\#x007E;</mo></mover>}}
\begin{document}
\EndPreamble
"""


def adapt_xetex_cyrillic(text: str) -> str:
    """Register Cyrillic before title/author tokens are read in the preamble.

    TeX4ht's late Babel hook only fixes text read after begin{document}.
    https://www.kodymirus.cz/tex4ht-doc/Configurations.html (Unicode)
    """
    if XETEX_CYRILLIC_COMPAT in text:
        return text
    return XETEX_CYRILLIC_COMPAT + "\n" + text


def adapt_luatex_unicode_fonts(text: str) -> str:
    """Use a Unicode font for an exact legacy T2A fontenc declaration.

    LuaLaTeX cannot use the classic T2A ``larm`` metrics reliably.  Keep this
    deliberately narrow: comments, macro-generated package loads, multiple
    options and all other font configurations remain untouched.
    """
    preamble, marker, document = text.partition(r"\begin{document}")
    if not marker or LUATEX_UNICODE_FONT_COMPAT in preamble:
        return text
    pattern = re.compile(
        r"(?m)^(?P<indent>[ \t]*)\\usepackage[ \t]*\[T2A\][ \t]*\{fontenc\}[ \t]*$"
    )
    preamble, count = pattern.subn(
        lambda match: match.group("indent") + LUATEX_UNICODE_FONT_COMPAT,
        preamble,
        count=1,
    )
    return preamble + marker + document if count else text


def adapt_cfrac_for_tex4ht(text: str) -> str:
    r"""Use equivalent display fractions that don't trip TeX4ht conditionals.

    ``\\cfrac`` and ``\\dfrac`` have the same display size in the generated
    MathML.  Preserve examples in comments, inline verbatim and literal code
    environments because they aren't executable TeX commands.
    """
    pattern = re.compile(
        r"(?P<protected>%[^\n]*|\\verb\*?(?P<delimiter>[^\w\s]).*?(?P=delimiter)"
        r"|\\begin\{(?P<literal>verbatim\*?|lstlisting|minted)\}.*?"
        r"\\end\{(?P=literal)\})|(?P<command>\\cfrac)(?![A-Za-z@])",
        re.DOTALL,
    )
    return pattern.sub(
        lambda match: match.group(0) if match.group("protected") else r"\dfrac",
        text,
    )


def adapt_multline_for_tex4ht(text: str) -> str:
    r"""Render ``multline`` through the better-supported ``aligned`` MathML path.

    The transformation is confined to executable environments in the staged
    copy.  It keeps every formula token, line break and label unchanged while
    avoiding TeX4ht failures at ``\\end{multline}`` seen with TeX Live 2025.
    Comments and literal examples are deliberately left alone.
    """
    protected = re.compile(
        r"(?P<literal>\\begin\{(?P<name>verbatim\*?|lstlisting|minted)\}.*?"
        r"\\end\{(?P=name)\})|(?P<comment>%[^\n]*)|"
        r"(?P<begin>\\begin\{multline(?P<star>\*)?\})|"
        r"(?P<end>\\end\{multline(?P<endstar>\*)?\})",
        re.DOTALL,
    )

    def replace(match: re.Match[str]) -> str:
        if match.group("begin"):
            star = "*" if match.group("star") else ""
            return rf"\begin{{equation{star}}}\begin{{aligned}}"
        if match.group("end"):
            star = "*" if match.group("endstar") else ""
            return rf"\end{{aligned}}\end{{equation{star}}}"
        return match.group(0)

    return protected.sub(replace, text)


def adapt_literal_relations_for_tex4ht(text: str) -> str:
    r"""Spell literal comparison characters explicitly inside TeX math only.

    Some current TeX4ht builds serialize a literal ``<`` as a broken
    ``mstyle`` fragment.  Explicit TeX relation mathchars have the same
    semantics without relying on optional ``\\lt``/``\\gt`` definitions.
    Text, comments, escaped characters and literal environments are untouched.
    """
    math_delimiters = re.compile(
        r"%[^\n]*|\\verb\*?(?P<delim>[^\w\s]).*?(?P=delim)"
        r"|\\begin\{(?P<literal>verbatim\*?|lstlisting|minted)\}.*?\\end\{(?P=literal)\}"
        r"|\\[%\\$]|\$\$?|\\[\[\]()]"
        r"|\\(?:begin|end)\{(?:equation\*?|align\*?|gather\*?|multline\*?|displaymath|math|eqnarray\*?)\}",
        re.DOTALL,
    )
    end_token: str | None = None
    formula_start = last = 0
    output: list[str] = []
    for token in math_delimiters.finditer(text):
        value = token.group(0)
        if end_token is None:
            if value in ("$", "$$", r"\(", r"\["):
                end_token = {r"\(": r"\)", r"\[": r"\]"}.get(value, value)
            elif value.startswith(r"\begin{") and not token.group("literal"):
                end_token = value.replace(r"\begin", r"\end", 1)
            else:
                continue
            formula_start = token.end()
        elif value == end_token:
            formula = text[formula_start : token.start()]
            formula = formula.replace("<", r'\mathchar"313C ').replace(
                ">", r'\mathchar"313E '
            )
            output.extend((text[last:formula_start], formula))
            last = token.start()
            end_token = None
    output.append(text[last:])
    return "".join(output)


def adapt_miktex_paragraphs(text: str) -> str:
    """Backport TeX4ht's paragraph-context workaround for modern TeX engines.

    The 2023 MiKTeX TeX4ht leaves par empty inside alignments. New engines
    insert paragraph tokens there indefinitely. TeX4ht 2025 disables that
    behavior with partokencontext=0; guard it for older engines.
    https://www.tug.org/tex4ht/changelog.html (2025-12-14)
    """
    if MIKTEX_PARAGRAPH_COMPAT in text:
        return text
    return MIKTEX_PARAGRAPH_COMPAT + "\n" + text


def normalize_reference_keys(text: str) -> str:
    """Encode non-ASCII reference keys consistently across included files."""

    def replace(match):
        keys = match.group(2).split(",")
        keys = [
            key if key.isascii() else "texkey-" + key.encode("utf-8").hex()
            for key in keys
        ]
        return match.group(1) + "{" + ",".join(keys) + "}"

    return re.sub(
        r"(\\(?:label|ref|pageref|eqref|autoref|cref|Cref|vref|eq)\*?\s*)\{([^{}]+)\}",
        replace,
        text,
    )


def normalize_prime_superscripts(text: str) -> str:
    """Write TeX's combined prime/superscript explicitly for TeX4ht."""

    def replace(match):
        power = match.group(3)
        if power.startswith("{"):
            power = power[1:-1]
        return (
            match.group(1) + "^{" + r"\prime" * len(match.group(2)) + " " + power + "}"
        )

    return re.sub(r"([A-Za-z])('+)[ \t]*\^(\{[^{}]*\}|[A-Za-z0-9])", replace, text)

from tex_compatibility import normalize_prime_superscripts, normalize_reference_keys


def test_xetex_registers_cyrillic_before_preamble_without_changing_fonts():
    from tex_compatibility import XETEX_CYRILLIC_COMPAT, adapt_xetex_cyrillic

    source = (
        r"\documentclass{book}\title{Заголовок}\author{Автор}\begin{document}\maketitle"
    )
    result = adapt_xetex_cyrillic(source)
    assert result == XETEX_CYRILLIC_COMPAT + "\n" + source
    assert adapt_xetex_cyrillic(result) == result


def test_miktex_paragraph_workaround_is_guarded_and_idempotent():
    from tex_compatibility import MIKTEX_PARAGRAPH_COMPAT, adapt_miktex_paragraphs

    source = r"\documentclass{book}\title{Title}\begin{document}\maketitle Text\end{document}"
    result = adapt_miktex_paragraphs(source)
    assert result == MIKTEX_PARAGRAPH_COMPAT + "\n" + source
    assert adapt_miktex_paragraphs(result) == result


def test_unicode_label_and_references_share_ascii_key():
    source = r"\label{eq:5с} \eqref{eq:5с} \ref{ascii} \cref{eq:5с,ascii}"
    result = normalize_reference_keys(source)
    key = "texkey-" + "eq:5с".encode().hex()
    assert (
        result == rf"\label{{{key}}} \eqref{{{key}}} \ref{{ascii}} \cref{{{key},ascii}}"
    )
    assert normalize_reference_keys(result) == result


def test_prime_and_power_are_kept_in_one_superscript():
    assert (
        normalize_prime_superscripts("x'^2_1 + y''^{n+1}_2")
        == r"x^{\prime 2}_1 + y^{\prime\prime n+1}_2"
    )
    assert normalize_prime_superscripts("x'_1") == "x'_1"


def test_luatex_replaces_only_exact_t2a_fontenc_in_preamble():
    from tex_compatibility import LUATEX_UNICODE_FONT_COMPAT, adapt_luatex_unicode_fonts

    source = "% \\usepackage[T2A]{fontenc}\n\\usepackage[T2A]{fontenc}\n\\begin{document}\ntext"
    result = adapt_luatex_unicode_fonts(source)

    assert result.startswith(
        "% \\usepackage[T2A]{fontenc}\n" + LUATEX_UNICODE_FONT_COMPAT
    )
    assert result.endswith("\\begin{document}\ntext")
    assert adapt_luatex_unicode_fonts(result) == result


def test_luatex_keeps_non_exact_font_configuration_unchanged():
    from tex_compatibility import adapt_luatex_unicode_fonts

    source = "\\usepackage[T1,T2A]{fontenc}\n\\begin{document}text"

    assert adapt_luatex_unicode_fonts(source) == source


def test_cfrac_replacement_skips_literal_examples():
    from tex_compatibility import adapt_cfrac_for_tex4ht

    source = (
        "\\cfrac{1}{2}\n"
        "% \\cfrac{comment}{example}\n"
        "\\verb|\\cfrac{verbatim}{example}|\n"
        "\\begin{verbatim}\\cfrac{block}{example}\\end{verbatim}"
    )

    result = adapt_cfrac_for_tex4ht(source)

    assert result.startswith("\\dfrac{1}{2}")
    assert "% \\cfrac{comment}{example}" in result
    assert "\\verb|\\cfrac{verbatim}{example}|" in result
    assert "\\begin{verbatim}\\cfrac{block}{example}\\end{verbatim}" in result


def test_multline_replacement_preserves_contents_and_skips_literal_examples():
    from tex_compatibility import adapt_multline_for_tex4ht

    source = (
        "\\begin{multline}a=b+\\\\\n+c\\label{eq:x}\\end{multline}\n"
        "% \\begin{multline}comment\\end{multline}\n"
        "\\begin{verbatim}\\begin{multline}literal\\end{multline}\\end{verbatim}"
    )

    result = adapt_multline_for_tex4ht(source)

    assert result.startswith(
        "\\begin{equation}\\begin{aligned}a=b+\\\\\n"
        "+c\\label{eq:x}\\end{aligned}\\end{equation}"
    )
    assert "% \\begin{multline}comment\\end{multline}" in result
    assert (
        "\\begin{verbatim}\\begin{multline}literal\\end{multline}\\end{verbatim}"
        in result
    )


def test_literal_relations_are_rewritten_only_in_math():
    from tex_compatibility import adapt_literal_relations_for_tex4ht

    source = (
        "text <tag> $a<0, b>1$ % $comment<2$\n"
        "\\[x<y\\] \\verb|$z<3$|\n"
        "\\begin{verbatim}$q<4$\\end{verbatim}"
    )

    result = adapt_literal_relations_for_tex4ht(source)

    assert 'text <tag> $a\\mathchar"313C 0, b\\mathchar"313E 1$' in result
    assert "% $comment<2$" in result
    assert '\\[x\\mathchar"313C y\\]' in result
    assert r"\verb|$z<3$|" in result
    assert r"\begin{verbatim}$q<4$\end{verbatim}" in result

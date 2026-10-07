from tex_source_validation import repair_tex_source, validate_tex_source


def test_repairs_confirmed_document_errors_and_is_idempotent():
    source = '\n'.join([
        r'$\alpha = 1 \), \( \beta = 1 $,',
        r'Если $ p \geq q \), \( E[X] = +\infty $',
        r'($ p = 0.4 \), \( q = 0.6 $)',
        r'{\itПример для ЦПТ}.',
    ])
    fixed, changes = repair_tex_source(source)
    assert fixed == '\n'.join([
        r'$\alpha = 1 $, $ \beta = 1 $,',
        r'Если $ p \geq q $, $ E[X] = +\infty $',
        r'($ p = 0.4 $, $ q = 0.6 $)',
        r'{\it Пример для ЦПТ}.',
    ])
    assert len(changes) == 4
    assert changes[-1].startswith('Line 4:')
    assert len(validate_tex_source(source)) == 4
    assert validate_tex_source(fixed) == []
    assert repair_tex_source(fixed) == (fixed, [])


def test_protected_examples_and_valid_math_are_unchanged():
    example = r'$a \), \( b$ {\itПример}'
    source = '\n'.join([
        '% ' + example,
        r'\verb|' + example + '|',
        r'\begin{verbatim}' + example + r'\end{verbatim}',
        r'\begin{lstlisting}' + example + r'\end{lstlisting}',
        r'\begin{minted}' + example + r'\end{minted}',
        r'$a$, $b$ and \(c\), \(d\)',
        r'$$a + b$$',
        r'\$a \), \( b\$',
        r'\\itПример',
    ])
    assert repair_tex_source(source) == (source, [])


def test_malformed_or_ambiguous_delimiters_are_not_guessed():
    source = r'$a \) b$' + '\n' + r'$a \), \( b' + '\n' + r'$$a \), \( b$$'
    assert repair_tex_source(source) == (source, [])


def test_body_tikz_library_moves_before_babel_activation_without_losing_text():
    source = '\n'.join([r'\usepackage[russian]{babel}', r'\usepackage{tikz}',
                        r'\begin{document}', r'\usetikzlibrary{arrows.meta}. % keep', 'Text'])
    fixed, changes = repair_tex_source(source)
    assert fixed.index(r'\usetikzlibrary{arrows.meta}') < fixed.index(r'\begin{document}')
    assert '. % keep\nText' in fixed
    assert len(changes) == 1
    assert repair_tex_source(fixed) == (fixed, [])


def test_tikz_library_literal_example_is_not_moved():
    source = '\n'.join([r'\usepackage[russian]{babel}', r'\usepackage{tikz}',
                        r'\begin{document}', r'\begin{verbatim}',
                        r'\usetikzlibrary{arrows.meta}', r'\end{verbatim}'])
    assert repair_tex_source(source) == (source, [])


def test_commented_babel_package_does_not_trigger_tikz_repair():
    source = '\n'.join([r'% \usepackage[russian]{babel}', r'\usepackage{tikz}',
                        r'\begin{document}', r'\usetikzlibrary{arrows.meta}'])
    assert repair_tex_source(source) == (source, [])

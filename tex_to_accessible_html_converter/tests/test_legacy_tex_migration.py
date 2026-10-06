from legacy_tex_migration import modernize_legacy_text


def document(body):
    return r'\documentclass{article}\begin{document}' + body + r'\end{document}'


def test_grouped_text_switches_preserve_normalfont_reset_and_scope():
    source = document(r'{\it Пример} {\bf Bold} {\rm Roman}')
    fixed, report = modernize_legacy_text(source)
    assert fixed == document(r'{\normalfont\itshape  Пример} {\normalfont\bfseries  Bold} {\normalfont\rmfamily  Roman}')
    assert [item['old'] for item in report] == [r'\it', r'\bf', r'\rm']
    assert modernize_legacy_text(fixed) == (fixed, [])


def test_math_comments_verbatim_and_preamble_are_preserved():
    body = '\n'.join([
        r'% {\it example}', r'\verb|{\it example}|',
        r'\begin{verbatim}{\it example}\end{verbatim}',
        r'${\it x}$', r'\({\bf x}\)', r'\[{\rm x}\]',
        r'\begin{align}{\it x}\end{align}', r'{\it Text}',
    ])
    source = r'\newcommand{\example}{{\it preamble}}' + document(body)
    fixed, report = modernize_legacy_text(source)
    assert len(report) == 1
    assert report[0]['line'] == 8
    assert fixed == source.replace(r'{\it Text}', r'{\normalfont\itshape  Text}')


def test_redefined_commands_and_unguarded_font_switches_are_preserved():
    source = document(r'\it Text {\italic x}')
    assert modernize_legacy_text(source) == (source, [])
    overridden = r'\renewcommand{\it}{custom}' + document(r'{\it text}')
    assert modernize_legacy_text(overridden) == (overridden, [])

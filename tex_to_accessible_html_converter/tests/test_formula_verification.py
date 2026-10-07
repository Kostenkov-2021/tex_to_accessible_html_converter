import pytest

from formula_verification import verify_formulas
from mathml_validation import validate_mathml_structure


def document(formula):
    return r'\documentclass{article}\begin{document}$' + formula + r'$\end{document}'


def math(body):
    return '<math xmlns="http://www.w3.org/1998/Math/MathML">' + body + '</math>'


@pytest.mark.parametrize('tex,body', [
    ('x+12', '<mi>x</mi><mo>+</mo><mn>12</mn>'),
    ('12', '<mn>1</mn><mn>2</mn>'),
    (r'\frac{x+1}{y}', '<mfrac><mrow><mi>x</mi><mo>+</mo><mn>1</mn></mrow><mi>y</mi></mfrac>'),
    ('x_1^2', '<msubsup><mi>x</mi><mn>1</mn><mn>2</mn></msubsup>'),
    ('x^2_1', '<msubsup><mi>x</mi><mn>1</mn><mn>2</mn></msubsup>'),
    (r'\sqrt{x}', '<msqrt><mi>x</mi></msqrt>'),
    (r'\sqrt[3]{x}', '<mroot><mi>x</mi><mn>3</mn></mroot>'),
    (r'\alpha\leq 0', '<mi>α</mi><mo>&le;</mo><mn>0</mn>'),
    (r'\begin{matrix}a&b\\c&d\end{matrix}', '<mtable><mtr><mtd><mi>a</mi></mtd><mtd><mi>b</mi></mtd></mtr><mtr><mtd><mi>c</mi></mtd><mtd><mi>d</mi></mtd></mtr></mtable>'),
])
def test_supported_notation_is_confirmed(tex, body):
    html, report = verify_formulas(document(tex), math(body))
    assert report['status'] == 'confirmed', report
    assert report['semantic_equivalence'] == 'not_proven'
    assert 'data-tex-formula-id="formula-1"' in html
    again, repeated = verify_formulas(document(tex), html)
    assert again == html
    assert repeated['status'] == 'confirmed'


@pytest.mark.parametrize('tex,body', [
    ('x^2', '<msup><mi>x</mi><mn>3</mn></msup>'),
    ('x_1', '<msup><mi>x</mi><mn>1</mn></msup>'),
    (r'\frac{a}{b}', '<mfrac><mi>b</mi><mi>a</mi></mfrac>'),
    ('x+x', '<mn>2</mn><mi>x</mi>'),
    ('x+y', '<mi>y</mi><mo>+</mo><mi>x</mi>'),
    ('x', '<mn>x</mn>'),
    ('x', '<mo>x</mo>'),
])
def test_structural_or_symbol_changes_are_mismatches(tex, body):
    _, report = verify_formulas(document(tex), math(body))
    assert report['status'] == 'mismatch'
    assert report['errors']
    assert report['formulas'][0]['expected'] != report['formulas'][0]['actual']


@pytest.mark.parametrize('tex,body', [
    (r'\custom{x}', '<mi>x</mi>'),
    (r'\mathbf{x}', '<mi mathvariant="bold">x</mi>'),
    ('x', '<menclose><mi>x</mi></menclose>'),
    ('x', '<mi mathvariant="bold">x</mi>'),
])
def test_unknown_notation_is_not_reported_as_mismatch(tex, body):
    html, report = verify_formulas(document(tex), math(body))
    assert report['status'] == 'unsupported'
    assert not report['errors']
    assert 'data-tex-formula-id' not in html


@pytest.mark.parametrize('extra', [r'\input{chapter}', r'\def\f{x}', r'\iftrue', r'\tableofcontents', r'\customtext'])
def test_dynamic_expansion_disables_positional_matching(extra):
    source = document('x').replace(r'\begin{document}', extra + r'\begin{document}')
    _, report = verify_formulas(source, math('<mi>y</mi>'))
    assert report['status'] == 'unsupported'
    assert not report['errors']


def test_comments_literals_and_scripts_do_not_count_as_formulas():
    source = document('x').replace('$x$', '% $ignored$\n' + r'\verb|$ignored$| $x$')
    html = '<!-- <math>fake</math> --><script>"<math>fake</math>"</script>' + math('<mi>x</mi>')
    _, report = verify_formulas(source, html)
    assert report['status'] == 'confirmed'
    assert report['source_count'] == report['output_count'] == 1
    assert report['formulas'][0]['line'] == 2


@pytest.mark.parametrize('html', ['', math('<mi>x</mi>') + math('<mi>y</mi>')])
def test_missing_or_extra_formula_is_detected(html):
    _, report = verify_formulas(document('x'), html)
    assert report['status'] == 'mismatch'


def test_order_and_semantics_annotation():
    source = document('x').replace('$x$', r'\(x\)\[y\]')
    html = math('<semantics><mi>x</mi><annotation encoding="application/x-tex">wrong</annotation></semantics>') + math('<mi>y</mi>')
    _, report = verify_formulas(source, html)
    assert report['status'] == 'confirmed'
    _, report = verify_formulas(source, math('<mi>y</mi>') + math('<mi>x</mi>'))
    assert report['status'] == 'mismatch'


def test_unbraced_script_uses_one_tex_token():
    _, report = verify_formulas(document('x^12'), math('<msup><mi>x</mi><mn>1</mn></msup><mn>2</mn>'))
    assert report['status'] == 'confirmed'
    _, report = verify_formulas(document('x^12'), math('<msup><mi>x</mi><mn>12</mn></msup>'))
    assert report['status'] == 'mismatch'


def test_math_inside_text_argument_is_unsupported():
    _, report = verify_formulas(document(r'x+\text{$y$}'), math('<mi>x</mi><mo>+</mo><mi>y</mi>'))
    assert report['status'] == 'unsupported'


def test_escaped_dollar_inside_formula_is_not_silently_discarded():
    _, report = verify_formulas(document(r'x\$y'), math('<mi>x</mi><mi>y</mi>'))
    assert report['status'] == 'unsupported'


def test_nested_mathml_tokens_are_rejected_but_html_in_mtext_is_allowed():
    assert validate_mathml_structure(math('<mo><mi>sin</mi><mo>&#x2061;</mo></mo>'))
    assert not validate_mathml_structure(math('<mtext><span xmlns="http://www.w3.org/1999/xhtml">text</span></mtext>'))

import xml.etree.ElementTree as ET

import pytest

from mathml_fidelity import MATHML, MI, repair_mathml_fidelity
from tex_compatibility import isolate_unscripted_operators


def math(body):
    return f'<math xmlns="{MATHML}">{body}</math>'


@pytest.mark.parametrize('wrapper', ['mi', 'mo'])
def test_empty_token_wrapping_function_keeps_application_with_argument(wrapper):
    source = math(f'<{wrapper}><mi>sin</mi><mo>&#x2061;</mo></{wrapper}><mi>x</mi>')
    result = repair_mathml_fidelity(source)
    root = ET.fromstring(result)
    assert [node.tag for node in root] == [MI, f'{{{MATHML}}}mo', MI]
    assert [node.text for node in root] == ['sin', '\u2061', 'x']
    assert repair_mathml_fidelity(result) == result


def test_unknown_or_nonempty_nested_token_is_not_guessed():
    source = math('<mo>prefix<mi>sin</mi><mo>&#x2061;</mo></mo>')
    assert repair_mathml_fidelity(source) == source


@pytest.mark.parametrize('name', ['arg', 'ker', 'customOperator'])
def test_additional_standard_function_wrappers_preserve_application(name):
    source = math(f'<mo><mi class="loglike">{name}</mi><mo>&#x2061;</mo></mo><mi>z</mi>')
    root = ET.fromstring(repair_mathml_fidelity(source))
    assert [node.text for node in root] == [name, '\u2061', 'z']
    assert root[0].get('class') == 'loglike'


@pytest.mark.parametrize('wrapper', ['mi class="qopname"', 'mo'])
@pytest.mark.parametrize('prime_text', ['′', '″', '‴', '⁗'])
def test_nested_double_prime_retains_derivative_symbol(wrapper, prime_text):
    tag = wrapper.split()[0]
    source = math(f'<msup><mi>G</mi><{wrapper}><mi>{prime_text}</mi></{tag}></msup>')
    fixed = repair_mathml_fidelity(source)
    prime = ET.fromstring(fixed)[0][1]
    assert prime.tag == f'{{{MATHML}}}mo'
    assert prime.text == prime_text and not len(prime)
    assert repair_mathml_fidelity(fixed) == fixed


def test_derivative_prime_does_not_keep_spurious_function_application():
    source = math('<msubsup><mi>G</mi><mi>X</mi><mrow><mi class="qopname"><mi>″</mi></mi><mo>&#x2061;</mo></mrow></msubsup>')
    fixed = repair_mathml_fidelity(source)
    assert '\u2061' not in ''.join(ET.fromstring(fixed).itertext())
    assert '″' in ''.join(ET.fromstring(fixed).itertext())
    assert repair_mathml_fidelity(fixed) == fixed


def test_prime_wrapper_preserves_style_classes():
    root = ET.fromstring(repair_mathml_fidelity(math('<mi class="qopname styled"><mi>″</mi></mi>')))
    assert root[0].get('class') == 'styled'
    assert root[0].text == '″'


def test_function_wrapper_preserves_qopname_class():
    source = math('<mi class="qopname"><mi class="loglike">tan</mi><mo>&#x2061;</mo></mi>')
    root = ET.fromstring(repair_mathml_fidelity(source))
    assert root[0].tag == MI
    assert set(root[0].get('class').split()) == {'loglike', 'qopname'}


def test_repaired_function_wrapper_does_not_duplicate_application():
    source = math('<mi class="qopname"><mi>sin</mi><mo>&#x2061;</mo></mi><mo> &#x2061; </mo><mi>x</mi>')
    result = repair_mathml_fidelity(source)
    root = ET.fromstring(result)
    assert len(root) == 3
    assert sum(node.text == '\u2061' for node in root.iter()) == 1
    assert repair_mathml_fidelity(result) == result


def test_broken_miktex_relation_wrapper_is_repaired_before_xml_parsing():
    source = math(
        '<mrow><mi>D</mi><mstyle class="MathClass-rel" stretchy="false"> '
        "&lt;/mo&gt; <mn>0</mn></mstyle></mrow>"
    )

    result = repair_mathml_fidelity(source)
    root = ET.fromstring(result)

    assert [child.tag for child in root[0]] == [
        MI,
        f"{{{MATHML}}}mo",
        f"{{{MATHML}}}mn",
    ]
    assert root[0][1].text == "<"
    assert repair_mathml_fidelity(result) == result


def test_text_relation_identifiers_become_operator_tokens():
    source = math(
        "<mrow><mn>36</mn><mi>&lt;</mi><mn>0</mn>"
        '<mi mathvariant="italic">&#x1D44E;&gt;&#x1D44F;</mi></mrow>'
    )

    root = ET.fromstring(repair_mathml_fidelity(source))

    assert [(node.tag, node.text) for node in root[0]] == [
        (f"{{{MATHML}}}mn", "36"),
        (f"{{{MATHML}}}mo", "<"),
        (f"{{{MATHML}}}mn", "0"),
        (MI, "a"),
        (f"{{{MATHML}}}mo", ">"),
        (MI, "b"),
    ]


@pytest.mark.parametrize(
    ("prefix", "last", "expected"),
    [
        ("<mn>1</mn>", "0", "10"),
        ("<mn>0</mn><mo>.</mo>", "6", "0.6"),
        ("<mn>12</mn>", "0", "120"),
    ],
)
def test_entire_number_is_power_base(prefix, last, expected):
    result = repair_mathml_fidelity(
        math(
            f"<mrow>{prefix}<msup><mrow><mn>{last}</mn></mrow><mn>3</mn></msup></mrow>"
        )
    )
    root = ET.fromstring(result)
    base = root.find(f".//{{{MATHML}}}msup")[0]
    assert "".join(node.text or "" for node in base.iter()) == expected
    assert repair_mathml_fidelity(result) == result


@pytest.mark.parametrize(
    "body",
    [
        '<mn>1</mn><mspace width="1em"/><msup><mn>0</mn><mn>3</mn></msup>',
        "<mfrac><mn>1</mn><msup><mn>2</mn><mn>3</mn></msup></mfrac>",
        "<mn>1</mn><mo>,</mo><msup><mn>2</mn><mn>3</mn></msup>",
        "<mrow><mn>1</mn></mrow><msup><mn>2</mn><mn>3</mn></msup>",
        "<mn>1</mn><mo>+</mo><msup><mn>2</mn><mn>3</mn></msup>",
        "<mn>1</mn>unexpected text<msup><mn>2</mn><mn>3</mn></msup>",
    ],
)
def test_does_not_join_separate_operands(body):
    original = math(body)
    assert repair_mathml_fidelity(original) == original


def test_only_unscripted_math_operators_are_isolated():
    source = r"\newcommand{\det}{x} text \det $\det Q=r_1^2$ \[\sum \sigma_i^2 + \sum_{i=1}^n i\]"
    result = isolate_unscripted_operators(source)
    assert (
        result
        == r"\newcommand{\det}{x} text \det ${\det} Q=r_1^2$ \[{\sum} \sigma_i^2 + \sum_{i=1}^n i\]"
    )
    assert isolate_unscripted_operators(result) == result


def test_comments_verbatim_and_explicit_limits_are_preserved():
    source = (
        "\\verb|$\\sum$| % $\\det$\n"
        + r"\begin{verbatim}$\sum$\end{verbatim} $\sum\limits_{i=1}^n i$"
    )
    assert isolate_unscripted_operators(source) == source


def test_well_formed_xml_with_incomplete_fraction_is_rejected():
    from mathml_validation import validate_mathml_structure

    assert validate_mathml_structure(math("<mfrac><mn>1</mn></mfrac>"))
    assert validate_mathml_structure(math("<merror><mtext>Failed</mtext></merror>"))


def test_miktex_operator_names_are_mathml_tokens():
    result = ET.fromstring(
        repair_mathml_fidelity(
            math('<mrow><mrow class="qopname"> cos</mrow><mi>x</mi></mrow>')
        )
    )
    operator = result[0][0]
    assert operator.tag == f"{{{MATHML}}}mi"
    assert operator.text == "cos"
    assert operator.get("mathvariant") == "normal"


def test_miktex_symbolic_operator_is_mo_not_identifier():
    result = ET.fromstring(
        repair_mathml_fidelity(math('<mrow class="qopname">∑</mrow>'))
    )
    assert result[0].tag == f"{{{MATHML}}}mo"
    assert result[0].text == "∑"


def test_styled_unicode_variables_are_separate_accessible_identifiers():
    source = math(
        '<mi>z</mi><mo class="MathClass-rel" stretchy="false">=</mo>'
        '<mi>a</mi><mo class="MathClass-bin" stretchy="false">+</mo>'
        '<mi mathvariant="italic">&#x1D456;&#x1D44F;</mi>'
    )

    result = repair_mathml_fidelity(source)
    root = ET.fromstring(result)
    identifiers = root.findall(f"./{{{MATHML}}}mi")

    assert [identifier.text for identifier in identifiers] == ["z", "a", "i", "b"]
    assert identifiers[-2].get("mathvariant") is None
    assert identifiers[-1].get("mathvariant") is None
    assert repair_mathml_fidelity(result) == result


def test_redundant_ib_wrapper_is_removed_without_losing_accessible_tokens():
    source = math(
        '<mrow><mi>z</mi><mo class="MathClass-rel" stretchy="false">=</mo>'
        '<mrow><mi>a</mi><mo class="MathClass-bin" stretchy="false">+</mo>'
        '<mrow><mi mathvariant="italic">i</mi><mo>&#x2062;</mo>'
        '<mi mathvariant="italic">b</mi></mrow></mrow></mrow>'
    )

    result = repair_mathml_fidelity(source)
    root = ET.fromstring(result)
    sum_row = root[0][2]

    assert [node.tag for node in sum_row] == [
        MI,
        f"{{{MATHML}}}mo",
        MI,
        f"{{{MATHML}}}mo",
        MI,
    ]
    assert [node.text for node in sum_row] == ["a", "+", "i", "\u2062", "b"]
    assert sum_row[2].get("mathvariant") is None
    assert sum_row[4].get("mathvariant") is None
    assert repair_mathml_fidelity(result) == result


def test_other_invisible_products_keep_their_grouping():
    source = math("<mrow><mi>x</mi><mo>&#x2062;</mo><mi>y</mi></mrow>")
    assert repair_mathml_fidelity(source) == source


def test_raw_text_inside_mrow_is_rejected():
    from mathml_validation import validate_mathml_structure

    assert validate_mathml_structure(math('<mrow class="qopname">sin</mrow>'))
    assert not validate_mathml_structure(math("<mi>sin</mi>"))


def test_subscript_applies_to_complete_norm():
    source = math(
        "<mrow><mo>∥</mo><mi>A</mi>"
        "<msub><mrow><mo>∥</mo></mrow><mrow><mi>p</mi></mrow></msub></mrow>"
    )

    root = ET.fromstring(repair_mathml_fidelity(source))
    script = root.find(f".//{{{MATHML}}}msub")

    assert [node.text for node in script[0]] == ["∥", "A", "∥"]
    assert script[0][0].get("fence") == "true"
    assert script[0][-1].get("fence") == "true"


def test_ascii_double_bars_become_one_norm_fence():
    source = math("<mrow><mo>|</mo><mo>|</mo><mi>x</mi><mo>|</mo><mo>|</mo></mrow>")

    root = ET.fromstring(repair_mathml_fidelity(source))

    assert [node.text for node in root[0]] == ["∥", "x", "∥"]


def test_bogus_equals_subscript_is_moved_after_norm():
    source = math(
        "<mrow><mo>∥</mo><mi>A</mi>"
        "<msub><mrow><mo>∥</mo></mrow><mrow><mo>=</mo></mrow></msub>"
        "<mo>∑</mo></mrow>"
    )

    root = ET.fromstring(repair_mathml_fidelity(source))

    assert [node.tag for node in root[0]] == [
        f"{{{MATHML}}}mrow",
        f"{{{MATHML}}}mo",
        f"{{{MATHML}}}mo",
    ]
    assert root[0][1].text == "="
    assert root[0][2].text == "∑"


@pytest.mark.parametrize(("source_number", "separator"), [("2.45", "."), ("2,86", ",")])
def test_decimal_separator_is_an_explicit_operator(source_number, separator):
    root = ET.fromstring(
        repair_mathml_fidelity(math(f"<mrow><mn>{source_number}</mn></mrow>"))
    )

    assert [node.text for node in root[0]] == [
        source_number[0],
        separator,
        source_number[2:],
    ]
    assert root[0][1].get("separator") == "true"


def test_touching_integer_digits_read_as_one_number():
    # A converter's fragmented 125 must retain the value rather than a list of digits.
    root = ET.fromstring(repair_mathml_fidelity(math("<mn>1</mn><mn>2</mn><mn>5</mn>")))
    assert len(root) == 1
    assert root[0].text == "125"


def test_separated_or_styled_numbers_are_not_joined():
    source = math('<mn>1</mn> <mn>2</mn><mspace width="1em"/><mn>3</mn><mn id="digit">4</mn>')
    root = ET.fromstring(repair_mathml_fidelity(source))
    assert [node.text for node in root if node.tag.endswith("mn")] == ["1", "2", "3", "4"]

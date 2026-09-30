import xml.etree.ElementTree as ET

import pytest

from mathml_fidelity import MATHML, MI, repair_mathml_fidelity
from tex_compatibility import isolate_unscripted_operators


def math(body):
    return f'<math xmlns="{MATHML}">{body}</math>'


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

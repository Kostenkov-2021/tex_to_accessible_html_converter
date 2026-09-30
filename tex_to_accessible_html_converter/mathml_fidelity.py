"""Conservative lexical repairs to TeX4ht's generated MathML."""

import re
import unicodedata
import xml.etree.ElementTree as ET

MATHML = "http://www.w3.org/1998/Math/MathML"
ET.register_namespace("", MATHML)
MATH = re.compile(r"<math\b.*?</math>", re.DOTALL)
SCRIPTS = {f"{{{MATHML}}}{tag}" for tag in ("msup", "msub", "msubsup")}
ROWS = {f"{{{MATHML}}}{tag}" for tag in ("math", "mrow", "mtd", "mstyle", "msqrt")}
MI = f"{{{MATHML}}}mi"
MO = f"{{{MATHML}}}mo"
MN = f"{{{MATHML}}}mn"
MROW = f"{{{MATHML}}}mrow"
BROKEN_RELATION = re.compile(
    r"<mstyle(?P<attrs>[^>]*\bclass=(?P<quote>['\"])MathClass-rel(?P=quote)[^>]*)>"
    r"\s*(?P<symbol>&lt;|&gt;)/mo&gt;(?P<body>.*?)</mstyle>",
    re.DOTALL,
)


def _is_mathematical_alphanumeric(character):
    """Return whether a character belongs to Unicode's styled math alphabet."""
    return 0x1D400 <= ord(character) <= 0x1D7FF


def _single_number(node):
    while node.tag == f"{{{MATHML}}}mrow" and len(node) == 1:
        node = node[0]
    if node.tag == f"{{{MATHML}}}mn" and not len(node):
        return node
    return None


def _is_accessible_ib_product(node):
    """Return whether node is only the redundant wrapper around i⁢b."""
    children = list(node)
    return (
        node.tag == MROW
        and not node.attrib
        and not (node.text or "").strip()
        and len(children) == 3
        and children[0].tag == MI
        and not len(children[0])
        and (children[0].text or "").strip() == "i"
        and children[1].tag == MO
        and not len(children[1])
        and (children[1].text or "").strip() == "\u2062"
        and children[2].tag == MI
        and not len(children[2])
        and (children[2].text or "").strip() == "b"
        and all(not (child.tail or "").strip() for child in children)
    )


def _single_token(node, tag, text=None):
    """Return a token through redundant one-child mrows."""
    while node.tag == MROW and len(node) == 1 and not (node.text or "").strip():
        node = node[0]
    if node.tag != tag or len(node):
        return None
    if text is not None and (node.text or "").strip() != text:
        return None
    return node


def _normalize_double_bars(parent):
    """Replace TeX ``||`` token pairs with the norm delimiter U+2225."""
    changed = False
    children = list(parent)
    index = 0
    while index + 1 < len(children):
        first = _single_token(children[index], MO, "|")
        second = _single_token(children[index + 1], MO, "|")
        if first is not None and second is not None:
            first.text = "∥"
            first.set("fence", "true")
            first.set("stretchy", "true")
            first.tail = second.tail
            parent.remove(children[index + 1])
            children.pop(index + 1)
            changed = True
            continue

        script = children[index + 1]
        scripted_bar = (
            _single_token(script[0], MO, "|")
            if script.tag in SCRIPTS and len(script)
            else None
        )
        if first is not None and scripted_bar is not None:
            scripted_bar.text = "∥"
            scripted_bar.set("fence", "true")
            scripted_bar.set("stretchy", "true")
            parent.remove(children[index])
            children.pop(index)
            changed = True
            continue
        index += 1
    return changed


def _group_scripted_fences(parent):
    """Make a subscript apply to a complete fenced value, not its closing bar."""
    changed = False
    children = list(parent)
    for script_index in range(len(children) - 1, -1, -1):
        script = children[script_index]
        if script.tag not in SCRIPTS or len(script) < 2:
            continue
        closing = _single_token(script[0], MO)
        if closing is None or (closing.text or "").strip() not in {"|", "∥"}:
            continue
        fence = (closing.text or "").strip()
        opening_index = None
        for index in range(script_index - 1, -1, -1):
            opening = _single_token(children[index], MO, fence)
            if opening is not None:
                opening_index = index
                break
        if opening_index is None:
            continue

        opening = _single_token(children[opening_index], MO, fence)
        opening.set("fence", "true")
        opening.set("stretchy", "true")
        closing.set("fence", "true")
        closing.set("stretchy", "true")
        fenced = ET.Element(MROW)
        for node in children[opening_index:script_index]:
            parent.remove(node)
            fenced.append(node)
        script[0] = fenced
        fenced.append(closing)

        # TeX ``\|A\|_ =`` makes '=' the subscript.  It unambiguously belongs
        # after the norm, so unwrap the bogus script and retain the relation.
        relation = _single_token(script[1], MO, "=")
        if script.tag == f"{{{MATHML}}}msub" and relation is not None:
            script_position = list(parent).index(script)
            fenced.tail = script.tail
            parent.remove(script)
            parent.insert(script_position, fenced)
            parent.insert(script_position + 1, relation)
        changed = True
    return changed


def repair_mathml_fidelity(html: str) -> str:
    """Restore operator tokens and numeric bases split at a script.

    Never cross mspace, another operator, or an explicit sibling mrow.
    Only changed math fragments are serialized; HTML outside math is untouched.
    """
    # MiKTeX TeX4ht sometimes escapes the opening relation token's closing
    # tag and changes its wrapper to mstyle. This swallows the rest of the
    # formula, so repair it before locating and parsing individual math nodes.
    html = BROKEN_RELATION.sub(
        lambda match: (
            f"<mo{match.group('attrs')}>{match.group('symbol')}</mo>"
            + match.group("body")
        ),
        html,
    )

    def repair(match):
        fragment = match[0]
        # Generated TeX4ht MathML uses numeric/XML entities. Leave other
        # encodings to the validator instead of risking lossy HTML parsing.
        try:
            root = ET.fromstring(fragment)
        except ET.ParseError:
            return fragment
        changed = False
        for parent in root.iter():
            if len(parent):
                changed = _normalize_double_bars(parent) or changed
                changed = _group_scripted_fences(parent) or changed
            if (
                parent.tag == f"{{{MATHML}}}mi"
                and not len(parent)
                and {"qopname", "MathClass-op"} & set(parent.get("class", "").split())
                and (parent.text or "").strip()
                and not any(c.isalpha() for c in (parent.text or ""))
            ):
                parent.tag = f"{{{MATHML}}}mo"
                parent.attrib.pop("mathvariant", None)
                changed = True
            for index, child in reversed(list(enumerate(list(parent)))):
                if child.tag == MN and not len(child):
                    decimal = re.fullmatch(r"([0-9]+)([.,])([0-9]+)", child.text or "")
                    if decimal:
                        integer = ET.Element(MN, child.attrib.copy())
                        integer.text = decimal.group(1)
                        separator = ET.Element(MO, {"separator": "true"})
                        separator.text = decimal.group(2)
                        fraction = ET.Element(MN, child.attrib.copy())
                        fraction.text = decimal.group(3)
                        fraction.tail = child.tail
                        parent.remove(child)
                        for token in reversed((integer, separator, fraction)):
                            parent.insert(index, token)
                        changed = True
            if (
                parent.tag == f"{{{MATHML}}}mrow"
                and not len(parent)
                and "qopname" in parent.get("class", "").split()
                and (parent.text or "").strip()
            ):
                parent.text = (parent.text or "").strip()
                parent.tag = f"{{{MATHML}}}" + (
                    "mi" if any(c.isalpha() for c in parent.text) else "mo"
                )
                if parent.tag.endswith("}mi"):
                    parent.set("mathvariant", "normal")
                changed = True
            # TeX4ht can combine adjacent variables into one token containing
            # styled Unicode letters. Some screen readers skip that token.
            # MathML models adjacent variables as separate identifiers; use
            # ordinary Unicode letters and retain the visual variant.
            for index, child in reversed(list(enumerate(list(parent)))):
                text = child.text or ""
                if (
                    child.tag == MI
                    and not len(child)
                    and any(c in "<>" for c in text)
                    and all(c in "<>" or _is_mathematical_alphanumeric(c) for c in text)
                ):
                    replacements = []
                    for character in unicodedata.normalize("NFKC", text):
                        if character in "<>":
                            token = ET.Element(
                                MO, {"class": "MathClass-rel", "stretchy": "false"}
                            )
                        else:
                            attributes = child.attrib.copy()
                            if attributes.get("mathvariant") == "italic":
                                attributes.pop("mathvariant")
                            token = ET.Element(MI, attributes)
                        token.text = character
                        replacements.append(token)
                    replacements[-1].tail = child.tail
                    parent.remove(child)
                    for token in reversed(replacements):
                        parent.insert(index, token)
                    changed = True
                    continue
                if (
                    child.tag != MI
                    or len(child)
                    or len(text) < 2
                    or not all(_is_mathematical_alphanumeric(c) for c in text)
                ):
                    continue
                normalized = unicodedata.normalize("NFKC", text)
                if len(normalized) != len(text):
                    continue
                replacements = []
                for character in normalized:
                    attributes = child.attrib.copy()
                    # A one-character mi is italic by default in MathML. An
                    # explicit italic variant makes Russian MathCAT Braille
                    # add typeform delimiters around every variable.
                    if attributes.get("mathvariant") == "italic":
                        attributes.pop("mathvariant")
                    token = ET.Element(MI, attributes)
                    token.text = character
                    replacements.append(token)
                replacements[-1].tail = child.tail
                parent.remove(child)
                for token in reversed(replacements):
                    parent.insert(index, token)
                changed = True
            # Keep the separate identifiers and invisible multiplication used
            # by screen readers, but remove TeX4ht's redundant visual group.
            for index, child in reversed(list(enumerate(list(parent)))):
                if not _is_accessible_ib_product(child):
                    continue
                replacements = list(child)
                for token in (replacements[0], replacements[2]):
                    if token.get("mathvariant") == "italic":
                        token.attrib.pop("mathvariant")
                replacements[-1].tail = child.tail
                parent.remove(child)
                for token in reversed(replacements):
                    parent.insert(index, token)
                changed = True
            if parent.tag not in ROWS:
                continue
            children = list(parent)
            for index, script in enumerate(children):
                if script.tag not in SCRIPTS or not len(script):
                    continue
                base = _single_number(script[0])
                if base is None or not re.fullmatch(r"[0-9]+", base.text or ""):
                    continue
                preceding: list[ET.Element] = []
                cursor = index - 1
                while cursor >= 0:
                    previous = children[cursor]
                    if (previous.tail or "").strip():
                        break
                    is_number = previous.tag == f"{{{MATHML}}}mn" and re.fullmatch(
                        r"[0-9]+(?:\.[0-9]+)?", previous.text or ""
                    )
                    is_decimal_point = (
                        previous.tag == f"{{{MATHML}}}mo" and previous.text == "."
                    )
                    if is_number or is_decimal_point:
                        preceding.insert(0, previous)
                    else:
                        break
                    cursor -= 1
                number = "".join(n.text or "" for n in preceding) + base.text
                if preceding and re.fullmatch(r"[0-9]+(?:\.[0-9]+)?", number):
                    base.text = number
                    for previous in preceding:
                        parent.remove(previous)
                    changed = True
        return ET.tostring(root, encoding="unicode") if changed else fragment

    return MATH.sub(repair, html)

"""Validate the structural integrity of generated MathML fragments."""

import html.entities
import re
import xml.etree.ElementTree as ET

ARITIES = {
    "mfrac": 2,
    "mroot": 2,
    "msub": 2,
    "msup": 2,
    "munder": 2,
    "mover": 2,
    "msubsup": 3,
    "munderover": 3,
}
ELEMENT_ONLY = {"math", "mrow", "mstyle", "msqrt", "mtd", *ARITIES}


def validate_mathml_structure(text: str) -> list[str]:
    """Check balanced math roots and XML structure before reporting success."""
    errors = []
    start = None
    count = 0
    for match in re.finditer(r"</?math\b[^>]*>", text, flags=re.IGNORECASE):
        if not match.group().startswith("</"):
            count += 1
            if start is not None:
                errors.append(f"MathML #{count}: nested or unclosed math element")
            start = match.start()
        elif start is None:
            errors.append("MathML: closing math tag without an opening tag")
        else:
            fragment = text[start : match.end()]

            def entity(m):
                name = m.group(1)
                if name in {"amp", "lt", "gt", "quot", "apos"}:
                    return m.group()
                value = html.entities.html5.get(name + ";")
                return (
                    m.group()
                    if value is None
                    else "".join(f"&#{ord(c)};" for c in value)
                )

            fragment = re.sub(r"&([A-Za-z][A-Za-z0-9]+);", entity, fragment)
            try:
                root = ET.fromstring(fragment)
                for node in root.iter():
                    tag = node.tag.rsplit("}", 1)[-1]
                    if tag in ARITIES and len(node) != ARITIES[tag]:
                        errors.append(
                            f"MathML #{count}: {tag} requires {ARITIES[tag]} children, got {len(node)}"
                        )
                    if tag == "merror":
                        errors.append(f"MathML #{count}: merror in generated formula")
                    if tag in {"mi", "mn", "mo", "ms", "mtext"} and any(
                        (child.tag.startswith("{http://www.w3.org/1998/Math/MathML}")
                         or ("}" not in child.tag and child.tag in {
                             "math", "mrow", "mstyle", "msqrt", "mi", "mn", "mo",
                             "mtext", "ms", "mtable", "mtr", "mtd", *ARITIES,
                         }))
                        and child.tag.rsplit("}", 1)[-1] not in {"mglyph", "malignmark"}
                        for child in node
                    ):
                        errors.append(f"MathML #{count}: mathematical element inside token {tag}")
                    has_raw_text = (node.text or "").strip() or any(
                        (child.tail or "").strip() for child in node
                    )
                    if tag in ELEMENT_ONLY and has_raw_text:
                        errors.append(
                            f"MathML #{count}: raw text outside a token in {tag}"
                        )
            except ET.ParseError as error:
                errors.append(f"MathML #{count}: {error}")
            start = None
    if start is not None:
        errors.append("MathML: unclosed math element at end of document")
    return errors

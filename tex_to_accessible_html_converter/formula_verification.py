"""Compare a conservative subset of TeX notation with Presentation MathML.

This checks notation, not algebraic equivalence. Unknown macros or ambiguous
document expansion disable positional matching rather than inventing a match.
References: https://www.w3.org/TR/mathml-core/ and LaTeX source2e documentation.
"""

from bisect import bisect_right
from html import entities
from html.parser import HTMLParser
import re
import xml.etree.ElementTree as ET


SYMBOLS = dict(zip(
    "alpha beta gamma delta epsilon theta lambda mu pi rho sigma tau phi psi omega Gamma Delta Theta Lambda Pi Sigma Phi Psi Omega".split(),
    "αβγδεθλμπρστφψωΓΔΘΛΠΣΦΨΩ",
))
SYMBOLS.update({"le": "≤", "leq": "≤", "ge": "≥", "geq": "≥",
                "neq": "≠", "ne": "≠", "times": "×", "cdot": "⋅",
                "pm": "±", "infty": "∞", "sum": "∑", "prod": "∏",
                "int": "∫", "in": "∈", "notin": "∉", "to": "→"})
SKIP = re.compile(
    r"%[^\n]*|\\verb\*?(?P<delimiter>[^\w\s]).*?(?P=delimiter)"
    r"|\\begin\{(?P<literal>verbatim\*?|lstlisting|minted)\}.*?\\end\{(?P=literal)\}"
    r"|\\[%$\\]", re.DOTALL,
)
SAFE_BODY_COMMANDS = {"begin", "end", "section", "subsection", "subsubsection",
                      "paragraph", "textbf", "textit", "emph", "item", "label",
                      "ref", "eqref", "par", "newline", "noindent"}
SAFE_ENVIRONMENTS = {"document", "itemize", "enumerate", "quote", "center"}


class Unsupported(ValueError):
    """The checker cannot faithfully interpret this notation."""


def row(children):
    flat = []
    for child in children:
        flat.extend(child[1] if child[0] == "row" else [child])
    merged = []
    for child in flat:
        if (merged and child[:2] == ("token", "number")
                and merged[-1][:2] == ("token", "number")
                and child[2].isdigit() and merged[-1][2].isdigit()):
            merged[-1] = token(merged[-1][2] + child[2])
        else:
            merged.append(child)
    flat = merged
    return flat[0] if len(flat) == 1 else ("row", tuple(flat))


def token(text, kind=None):
    if kind is None:
        kind = "number" if re.fullmatch(r"[0-9]+(?:\.[0-9]+)?", text) else (
            "identifier" if text.isalpha() else "operator"
        )
    return ("token", kind, text.replace("−", "-"))


class TeXNotation:
    def __init__(self, source):
        self.tokens = re.findall(r"\\[A-Za-z]+|\\.|[0-9]+(?:\.[0-9]+)?|[^\s]", source)
        self.index = 0

    def take(self):
        if self.index >= len(self.tokens):
            raise Unsupported("Incomplete TeX expression")
        value = self.tokens[self.index]
        self.index += 1
        return value

    def peek(self):
        return self.tokens[self.index] if self.index < len(self.tokens) else None

    def group(self):
        if self.take() != "{":
            raise Unsupported("Expected a braced argument")
        result = self.sequence({"}"})
        if self.take() != "}":
            raise Unsupported("Unclosed group")
        return result

    def argument(self):
        if self.peek() == "{":
            return self.group()
        if self.peek() and self.peek()[0].isdigit() and len(self.peek()) > 1:
            number = self.peek()
            self.tokens[self.index] = number[1:]
            return token(number[0])
        return self.atom()

    def environment(self):
        if self.take() != "{":
            raise Unsupported("Expected an environment name")
        parts = []
        while self.peek() not in {None, "}"}:
            parts.append(self.take())
        if self.take() != "}":
            raise Unsupported("Unclosed environment name")
        return "".join(parts)

    def atom(self):
        value = self.take()
        if value == "{":
            self.index -= 1
            return self.group()
        if value in {"}", "^", "_", "&", "'"}:
            raise Unsupported(f"Unsupported TeX token: {value}")
        if value in {r"\frac", r"\dfrac", r"\tfrac"}:
            return ("frac", self.group(), self.group())
        if value == r"\sqrt":
            degree = None
            if self.peek() == "[":
                self.take()
                degree = self.sequence({"]"})
                if self.take() != "]":
                    raise Unsupported("Unclosed root degree")
            body = self.group()
            return ("root", body, degree) if degree is not None else ("sqrt", body)
        if value == r"\begin":
            env = self.environment()
            if env not in {"matrix", "pmatrix", "bmatrix"}:
                raise Unsupported(f"Unsupported math environment: {env}")
            rows, cells = [], []
            while True:
                cells.append(self.sequence({"&", r"\\", r"\end"}))
                separator = self.take()
                if separator == "&":
                    continue
                rows.append(tuple(cells))
                cells = []
                if separator == r"\end":
                    if self.environment() != env:
                        raise Unsupported("Mismatched matrix environment")
                    break
            matrix = ("matrix", tuple(rows))
            return row([token("("), matrix, token(")")]) if env == "pmatrix" else (
                row([token("["), matrix, token("]")]) if env == "bmatrix" else matrix
            )
        if value.startswith("\\"):
            symbol = SYMBOLS.get(value[1:])
            if symbol is None:
                raise Unsupported(f"Unsupported TeX command: {value}")
            return token(symbol)
        if not (value.isascii() and (value.isalnum() or value in "+-=<>(),.;:[]|/!")):
            raise Unsupported(f"Unsupported TeX character: {value}")
        return token(value)

    def sequence(self, stops=frozenset()):
        children = []
        while self.peek() is not None and self.peek() not in stops:
            if self.peek() in {r"\,", r"\;", r"\!", r"\quad", r"\qquad"}:
                self.take()
                continue
            base = self.atom()
            sub = sup = None
            while self.peek() in {"^", "_"}:
                kind = self.take()
                if (kind == "^" and sup is not None) or (kind == "_" and sub is not None):
                    raise Unsupported("Repeated script")
                argument = self.argument()
                if kind == "^":
                    sup = argument
                else:
                    sub = argument
            children.append(("scripts", base, sub, sup) if sub is not None or sup is not None else base)
        return row(children)


def mathml_notation(node):
    tag = node.tag.rsplit("}", 1)[-1]
    if node.get("mathvariant") not in {None, "normal", "italic"}:
        raise Unsupported("Styled math alphabets are not supported")
    if tag in {"mi", "mn", "mo"}:
        if len(node):
            raise Unsupported("Markup inside a MathML token")
        value = (node.text or "").strip()
        if not value:
            raise Unsupported("Empty MathML token")
        return token(value, {"mi": "identifier", "mn": "number", "mo": "operator"}[tag])
    if (node.text or "").strip() or any((child.tail or "").strip() for child in node):
        raise Unsupported("Non-token MathML text")
    if tag == "semantics":
        if not len(node):
            raise Unsupported("Empty semantics element")
        return mathml_notation(node[0])
    if tag in {"math", "mrow", "mstyle", "mtd"}:
        return row([mathml_notation(child) for child in node])
    if tag == "msqrt":
        return ("sqrt", row([mathml_notation(child) for child in node]))
    if tag in {"mfrac", "mroot"} and len(node) == 2:
        return ("frac" if tag == "mfrac" else "root", *map(mathml_notation, node))
    if tag in {"msub", "msup", "msubsup"} and len(node) == (3 if tag == "msubsup" else 2):
        base = mathml_notation(node[0])
        sub = mathml_notation(node[1]) if tag != "msup" else None
        sup = mathml_notation(node[-1]) if tag != "msub" else None
        return ("scripts", base, sub, sup)
    if tag == "mtable":
        rows = []
        for child in node:
            if child.tag.rsplit("}", 1)[-1] != "mtr":
                raise Unsupported("Unsupported matrix row")
            if any(cell.tag.rsplit("}", 1)[-1] != "mtd" for cell in child):
                raise Unsupported("Unsupported matrix cell")
            rows.append(tuple(mathml_notation(cell) for cell in child))
        return ("matrix", tuple(rows))
    raise Unsupported(f"Unsupported MathML element: {tag}")


class MathFragments(HTMLParser):
    def __init__(self, html):
        super().__init__(convert_charrefs=False)
        self.html = html
        self.lines = [0] + [m.end() for m in re.finditer("\n", html)]
        self.fragments = []
        self.start = None

    def source_offset(self):
        line, column = self.getpos()
        return self.lines[line - 1] + column

    def handle_starttag(self, tag, attrs):
        if tag == "math":
            if self.start is not None:
                raise Unsupported("Nested math roots")
            self.start = self.source_offset()

    def handle_endtag(self, tag):
        if tag == "math" and self.start is not None:
            end = self.html.find(">", self.source_offset()) + 1
            self.fragments.append((self.start, end, self.html[self.start:end]))
            self.start = None


def extract_formulas(source):
    """Extract only a static document with an unambiguous formula order."""
    def mask(match):
        if match[0] == r"\\":
            return match[0]
        if match[0] in {r"\$", r"\%"}:
            return "\ue000 "
        return "".join("\n" if c == "\n" else " " for c in match[0])
    masked = SKIP.sub(mask, source)
    document = re.search(r"\\begin\{document\}(.*?)\\end\{document\}", masked, re.DOTALL)
    if document is None:
        raise Unsupported("Document boundaries are unavailable")
    if re.search(r"\\(?:text|mbox|hbox|vbox|ensuremath|label|ref|eqref)\b", masked):
        raise Unsupported("Text or reference arguments require contextual TeX parsing")
    preamble = masked[:document.start()]
    if re.search(r"\\documentclass(?:\[[^]]*\])?\{(?!article\}|report\}|book\})", preamble):
        raise Unsupported("Unsupported document class")
    for packages in re.findall(r"\\usepackage(?:\[[^]]*\])?\{([^}]+)\}", preamble):
        if any(name.strip() not in {"amsmath", "amssymb"} for name in packages.split(",")):
            raise Unsupported("Package effects on formula expansion are not supported")
    if any(command not in {"documentclass", "usepackage"}
           for command in re.findall(r"\\([A-Za-z]+)", preamble)):
        raise Unsupported("Unsupported preamble command")
    if re.search(r"\\(?:def|gdef|edef|xdef|let|catcode|newcommand|renewcommand|providecommand|Declare\w+|newenvironment|renewenvironment|input|include|includeonly|if\w*|else|fi|csname|newcounter|addtocounter|setcounter)\b", masked):
        raise Unsupported("Macros, includes or conditional expansion prevent reliable matching")
    pattern = re.compile(r"\$\$.*?\$\$|\$(?!\$).*?\$|\\\(.*?\\\)|\\\[.*?\\\]|\\begin\{(math|displaymath|equation\*?)\}(.*?)\\end\{\1\}", re.DOTALL)
    formulas = []
    body = document.group(1)
    outside = list(body)
    newlines = [m.start() for m in re.finditer("\n", source)]
    for match in pattern.finditer(body):
        value = match[0]
        if match.group(1):
            content = match.group(2)
        else:
            width = 2 if value.startswith(("$$", "\\")) else 1
            content = value[width:-width]
        offset = document.start(1) + match.start()
        formulas.append({"id": f"formula-{len(formulas) + 1}",
                         "line": bisect_right(newlines, offset) + 1,
                         "tex": content})
        outside[match.start():match.end()] = " " * (match.end() - match.start())
    rest = "".join(outside)
    if "$" in rest or re.search(r"\\[()[\]]", rest):
        raise Unsupported("Unbalanced math delimiters")
    for command in re.findall(r"\\([A-Za-z]+)", rest):
        if command not in SAFE_BODY_COMMANDS:
            raise Unsupported(f"Document command prevents reliable matching: \\{command}")
    for env in re.findall(r"\\(?:begin|end)\{([^}]+)\}", rest):
        if env not in SAFE_ENVIRONMENTS:
            raise Unsupported(f"Document environment prevents reliable matching: {env}")
    return formulas


def _xml(fragment):
    def replace(match):
        name = match[1]
        if name in {"amp", "lt", "gt", "quot", "apos"}:
            return match[0]
        value = entities.html5.get(name + ";")
        return match[0] if value is None else "".join(f"&#{ord(c)};" for c in value)
    return ET.fromstring(re.sub(r"&([A-Za-z][A-Za-z0-9]+);", replace, fragment))


def first_difference(expected, actual, path="formula"):
    if type(expected) is not type(actual):
        return {"path": path, "expected": expected, "actual": actual}
    if isinstance(expected, tuple):
        if len(expected) != len(actual):
            return {"path": path, "expected": expected, "actual": actual}
        for index, (left, right) in enumerate(zip(expected, actual)):
            if left != right:
                return first_difference(left, right, f"{path}[{index}]")
    return {"path": path, "expected": expected, "actual": actual}


def verify_formulas(source, html):
    """Return annotated HTML and a machine-readable notation verification report."""
    report = {"status": "unsupported", "scope": "formula_notation",
              "semantic_equivalence": "not_proven", "formulas": [], "errors": []}
    try:
        formulas = extract_formulas(source)
        parser = MathFragments(html)
        parser.feed(html)
        parser.close()
        if parser.start is not None:
            raise Unsupported("Unclosed MathML root")
    except Unsupported as error:
        report["reason"] = str(error)
        return html, report
    report["source_count"] = len(formulas)
    report["output_count"] = len(parser.fragments)
    if len(formulas) != len(parser.fragments):
        report["status"] = "mismatch"
        report["errors"] = [f"Formula count differs: TeX {len(formulas)}, MathML {len(parser.fragments)}"]
        return html, report
    edits = []
    for formula, (start, end, fragment) in zip(formulas, parser.fragments):
        entry = dict(formula, status="unsupported")
        try:
            expected = TeXNotation(formula["tex"]).sequence()
            actual = mathml_notation(_xml(fragment))
            entry.update(expected=expected, actual=actual)
            entry["status"] = "confirmed" if expected == actual else "mismatch"
            if entry["status"] == "mismatch":
                difference = first_difference(expected, actual)
                entry["difference"] = difference
                message = (f"{formula['id']} (line {formula['line']}), {difference['path']}: "
                           f"expected {difference['expected']!r}, got {difference['actual']!r}")
                entry["reason"] = message
                report["errors"].append(message)
            else:
                opening_end = fragment.find(">")
                # Preserve the existing markup and IDs; add a source correspondence.
                if "data-tex-formula-id" not in fragment[:opening_end]:
                    fragment = fragment[:opening_end] + f' data-tex-formula-id="{formula["id"]}" data-tex-source-line="{formula["line"]}"' + fragment[opening_end:]
                    edits.append((start, end, fragment))
        except (Unsupported, ET.ParseError, RecursionError) as error:
            entry["reason"] = str(error)
        report["formulas"].append(entry)
    report["status"] = "mismatch" if report["errors"] else (
        "unsupported" if any(item["status"] == "unsupported" for item in report["formulas"]) else "confirmed"
    )
    parts, cursor = [], 0
    for start, end, replacement in edits:
        parts.extend([html[cursor:start], replacement])
        cursor = end
    parts.append(html[cursor:])
    return "".join(parts), report

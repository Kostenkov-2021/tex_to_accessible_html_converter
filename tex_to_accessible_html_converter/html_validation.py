"""Targeted checks for generated HTML, not a full HTML5 conformance checker.

Optional-end-tag elements are deliberately excluded from nesting checks.
MathML structure is validated separately using its XML representation.
"""

from html.parser import HTMLParser


REQUIRED_END = {
    "a", "div", "span", "main", "nav", "section", "article", "figure",
    "figcaption", "table", "caption", "h1", "h2", "h3", "h4", "h5", "h6",
    "title", "style", "script", "strong", "em", "b", "i", "pre",
}


class _GeneratedHTMLParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.errors = []
        self.stack = []
        self.ids = set()
        self.math_depth = 0

    def handle_starttag(self, tag, attrs):
        names = set()
        for name, value in attrs:
            if name in names:
                self.errors.append(f"Duplicate attribute {name} on {tag}")
            names.add(name)
            if name == "id" and value:
                if value in self.ids:
                    self.errors.append(f"Duplicate id: {value}")
                self.ids.add(value)
            if tag == "math" and name == "xmlns" and value != "http://www.w3.org/1998/Math/MathML":
                self.errors.append("Incorrect MathML namespace")
        if tag == "math":
            self.math_depth += 1
        if not self.math_depth and tag in REQUIRED_END:
            self.stack.append(tag)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_endtag(self, tag):
        if tag == "math":
            self.math_depth = max(0, self.math_depth - 1)
            return
        if self.math_depth:
            return
        if tag in REQUIRED_END:
            if self.stack and self.stack[-1] == tag:
                self.stack.pop()
            else:
                self.errors.append(f"Unexpected closing tag: {tag}")


def validate_html_structure(text: str) -> list[str]:
    """Find broken explicit nesting and ambiguous IDs/attributes in one pass."""
    parser = _GeneratedHTMLParser()
    parser.feed(text)
    parser.close()
    parser.errors.extend(f"Unclosed HTML element: {tag}" for tag in parser.stack)
    return parser.errors

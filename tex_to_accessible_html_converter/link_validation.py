"""Validate hyperlink destinations without executing TeX or fetching websites.

URL resolution follows document/base URLs; fragment IDs are case-sensitive.
References with TeX4ht auxiliary mappings get an additional label-target check.
"""

from html import escape, unescape
from html.parser import HTMLParser
from pathlib import Path
import re
from urllib.parse import unquote, urljoin, urlsplit
from urllib.request import url2pathname

from tex_compatibility import normalize_reference_keys
from tex_source_validation import TOKENS


class LinkInventory(HTMLParser):
    def __init__(self, text):
        super().__init__(convert_charrefs=True)
        self.targets = set()
        self.links = []
        self.base = None
        self.line_offsets = [0]
        self.line_offsets.extend(m.end() for m in re.finditer("\n", text))
        self.feed(text)
        self.close()

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if attrs.get("id"):
            self.targets.add(attrs["id"])
        if tag == "a" and attrs.get("name"):
            self.targets.add(attrs["name"])
        if tag == "base" and "href" in attrs and self.base is None:
            self.base = attrs["href"] or ""
        if tag in {"a", "area"} and "href" in attrs:
            line, column = self.getpos()
            self.links.append({"href": attrs["href"] or "", "line": line,
                               "offset": self.line_offsets[line - 1] + column,
                               "markup": self.get_starttag_text()})

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)


def repair_self_links(text, generated_name):
    """Make same-build-file links independent of the saved HTML's filename.

    Only an exact filename with an existing fragment is rewritten. A base URL,
    directory, query, unknown target, or external address prevents the repair.
    """
    inventory = LinkInventory(text)
    if inventory.base is not None:
        return text, []
    edits, repairs = [], []
    for link in inventory.links:
        try:
            url = urlsplit(link["href"])
        except ValueError:
            continue
        if (url.scheme or url.netloc or url.query or not url.fragment
                or unquote(url.path) not in {generated_name, "./" + generated_name}
                or unquote(url.fragment) not in inventory.targets):
            continue
        match = re.search(r'''(?<![\w:-])href\s*=\s*(?:"(?P<double>[^"]*)"|'(?P<single>[^']*)'|(?P<bare>[^\s>]+))''', link["markup"], re.I)
        if match is None:
            continue
        group = next(name for name in ("double", "single", "bare") if match.group(name) is not None)
        if unescape(match.group(group)) != link["href"]:
            continue
        start, end = match.span(group)
        edits.append((link["offset"] + start, link["offset"] + end,
                      escape("#" + url.fragment, quote=True)))
        repairs.append({"line": link["line"], "before": link["href"], "after": "#" + url.fragment})
    pieces, cursor = [], 0
    for start, end, replacement in edits:
        pieces.extend((text[cursor:start], replacement))
        cursor = end
    if edits:
        pieces.append(text[cursor:])
        text = "".join(pieces)
    return text, repairs


def validate_links(text, output_file, auxiliary=None, source=None):
    """Check local destinations at the publication location, recording limits."""
    output_file = Path(output_file).resolve()
    inventory = LinkInventory(text)
    document_url = output_file.as_uri()
    base_url = urljoin(document_url, inventory.base or "")
    cached = {output_file: inventory.targets}
    records, errors = [], []
    for link in inventory.links:
        record = {"href": link["href"], "line": link["line"]}
        records.append(record)
        try:
            address = link["href"].strip(" \t\r\n\f").replace("\t", "").replace("\r", "").replace("\n", "")
            url = urlsplit(urljoin(base_url, address))
            if url.scheme != "file" or url.netloc not in {"", "localhost"}:
                record.update(status="external_not_checked", resolved=url.geturl())
                continue
            target = Path(url2pathname(url.path)).resolve()
            record["target_file"] = str(target)
            if target != output_file and not target.is_file():
                raise ValueError("local destination file does not exist")
            fragment = unquote(url.fragment, encoding="utf-8", errors="replace")
            if not fragment:
                record["status"] = "confirmed"
                continue
            if ":~:" in fragment:
                record["status"] = "text_fragment_not_checked"
                continue
            if target not in cached:
                if target.suffix.lower() not in {".html", ".htm", ".xhtml"}:
                    record["status"] = "non_html_fragment_not_checked"
                    continue
                cached[target] = LinkInventory(target.read_text(encoding="utf-8")).targets
            record["fragment"] = fragment
            if fragment not in cached[target] and fragment.lower() != "top":
                raise ValueError("fragment target does not exist (IDs are case-sensitive)")
            record["status"] = "confirmed"
        except (OSError, ValueError, UnicodeError) as error:
            record.update(status="broken", reason=str(error))
            errors.append(f"Line {link['line']}: {link['href']!r}: {error}")
    labels, references, known_labels = [], [], set()
    partial_auxiliary = False
    if auxiliary is not None and Path(auxiliary).is_file():
        # Parse only the known TeX4ht output shape. Never evaluate auxiliary TeX.
        for line in Path(auxiliary).read_text(encoding="utf-8", errors="replace").splitlines():
            key_match = re.match(r"\\newlabel\{([^{}]+)\}", line)
            if key_match:
                known_labels.add(key_match[1])
            partial_auxiliary = partial_auxiliary or bool(re.match(r"\\@input\{", line))
            match = re.match(r"\\newlabel\{([^{}]+)\}\{\{\\rEfLiNK\{([^{}]+)\}", line)
            if match:
                key, fragment = match.groups()
                labels.append({"label": key, "fragment": fragment,
                               "status": "confirmed" if fragment in inventory.targets else "missing_target"})
        label_scope = "tex4ht_auxiliary_targets"
    else:
        label_scope = "auxiliary_unavailable"
    if source is not None:
        visible = TOKENS.sub(lambda match: "" if match.group("protected") else match[0], source)
        visible = normalize_reference_keys(visible)
        aliases = [match[1] for match in re.finditer(
            r"\\newcommand\s*\{\\([A-Za-z]+)\}\s*\[1\]\s*\{\s*\(?\s*\\ref\s*\{#1\}\s*\)?\s*\}", visible
        )]
        commands = "|".join(["ref", "pageref", "eqref", "autoref", "cref", "Cref", "vref", *aliases])
        mapped = {}
        for label in labels:
            mapped.setdefault(label["label"], set()).add(label["fragment"])
        for match in re.finditer(r"\\(?:" + commands + r")\*?\s*\{([^{}]+)\}", visible):
            for key in match[1].split(","):
                if "#" in key or "\\" in key:
                    continue  # A macro parameter is not an expanded reference.
                reference = {"label": key}
                references.append(reference)
                destinations = mapped.get(key, set())
                if len(destinations) == 1:
                    fragment = next(iter(destinations))
                    reference.update(fragment=fragment, status="label_target_confirmed" if fragment in inventory.targets else "missing_target")
                    if fragment not in inventory.targets:
                        errors.append(f"TeX reference {key!r}: mapped target {fragment!r} is missing")
                elif len(destinations) > 1:
                    reference["status"] = "ambiguous_label"
                    errors.append(f"TeX reference {key!r}: conflicting label destinations")
                elif label_scope == "auxiliary_unavailable" or partial_auxiliary or key in known_labels:
                    reference["status"] = "mapping_not_supported"
                else:
                    reference["status"] = "undefined_label"
                    errors.append(f"TeX reference {key!r}: label is undefined in the compilation auxiliary file")
    return {"status": "failed" if errors else "passed", "errors": errors,
            "links": records, "labels": labels, "references": references, "label_scope": label_scope,
            "semantic_intent": "not_proven", "external_requests": "not_performed"}

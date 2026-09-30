"""Check catalog syntax, translated format fields and deterministic compilation."""

import ast
import gettext
import io
from pathlib import Path
from string import Formatter
import sys
import tempfile

import polib

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "packaging"))
from compile_translations import read_messages, write_mo  # noqa: E402


def fields(text):
    return sorted((field, spec, conversion) for _, field, spec, conversion
                  in Formatter().parse(text) if field is not None)


source = root / "tex_to_accessible_html_converter/locales/ru/LC_MESSAGES/tex_to_accessible_html.po"
catalog = polib.pofile(str(source), check_for_duplicates=True)
errors = []
translated = {entry.msgid for entry in catalog if not entry.obsolete}
for module in (root / "tex_to_accessible_html_converter").glob("*.py"):
    tree = ast.parse(module.read_text(encoding="utf-8"), filename=str(module))
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id == "_" and node.args
                and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)
                and node.args[0].value not in translated):
            errors.append(f"Missing catalog entry in {module.name}:{node.lineno}: {node.args[0].value!r}")
for entry in catalog:
    if entry.obsolete:
        continue
    if "fuzzy" in entry.flags or not entry.msgstr:
        errors.append(f"Untranslated or fuzzy message: {entry.msgid!r}")
    elif fields(entry.msgid) != fields(entry.msgstr):
        errors.append(f"Mismatched format fields: {entry.msgid!r}")
if errors:
    raise SystemExit("\n".join(errors))
with tempfile.TemporaryDirectory() as temporary:
    destination = Path(temporary) / "catalog.mo"
    messages = read_messages(source)
    write_mo(messages, destination)
    first = destination.read_bytes()
    write_mo(messages, destination)
    if first != destination.read_bytes():
        raise SystemExit("Catalog compilation is not deterministic.")
    compiled = gettext.GNUTranslations(io.BytesIO(first))
    for entry in catalog:
        if not entry.obsolete and compiled.gettext(entry.msgid) != entry.msgstr:
            raise SystemExit(f"Compiled translation differs: {entry.msgid!r}")
print(f"Validated {len(catalog)} translations.")

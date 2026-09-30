"""Compile gettext PO files without requiring external gettext utilities."""

from __future__ import annotations

import ast
import struct
from pathlib import Path


def read_messages(path: Path) -> dict[str, str]:
    messages: dict[str, str] = {}
    msgid: list[str] = []
    msgstr: list[str] = []
    active: list[str] | None = None
    fuzzy = False

    def finish() -> None:
        nonlocal msgid, msgstr, fuzzy
        if msgid and not fuzzy:
            messages["".join(msgid)] = "".join(msgstr)
        msgid, msgstr, fuzzy = [], [], False

    for raw_line in path.read_text(encoding="utf-8").splitlines() + [""]:
        line = raw_line.strip()
        if line.startswith("#, ") and "fuzzy" in line:
            fuzzy = True
        elif line.startswith("msgid "):
            if msgid:
                finish()
            active = msgid
            active.append(ast.literal_eval(line[6:]))
        elif line.startswith("msgstr "):
            active = msgstr
            active.append(ast.literal_eval(line[7:]))
        elif line.startswith('"') and active is not None:
            active.append(ast.literal_eval(line))
        elif not line and msgid:
            finish()
            active = None
    return messages


def write_mo(messages: dict[str, str], destination: Path) -> None:
    keys = sorted(messages)
    ids = b"\0".join(key.encode("utf-8") for key in keys) + b"\0"
    strings = b"\0".join(messages[key].encode("utf-8") for key in keys) + b"\0"
    count = len(keys)
    key_offset = 28 + count * 16
    value_offset = key_offset + len(ids)
    key_table = []
    value_table = []
    cursor = 0
    value_cursor = 0
    for key in keys:
        key_bytes = key.encode("utf-8")
        value_bytes = messages[key].encode("utf-8")
        key_table.extend((len(key_bytes), key_offset + cursor))
        value_table.extend((len(value_bytes), value_offset + value_cursor))
        cursor += len(key_bytes) + 1
        value_cursor += len(value_bytes) + 1
    header = struct.pack("<7I", 0x950412DE, 0, count, 28, 28 + count * 8, 0, 0)
    destination.write_bytes(
        header + struct.pack(f"<{count * 2}I", *key_table)
        + struct.pack(f"<{count * 2}I", *value_table) + ids + strings
    )


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    source = root / "tex_to_accessible_html_converter/locales/ru/LC_MESSAGES/tex_to_accessible_html.po"
    write_mo(read_messages(source), source.with_suffix(".mo"))

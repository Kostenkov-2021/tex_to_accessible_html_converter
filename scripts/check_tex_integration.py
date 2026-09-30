"""Exercise the real CLI and inspect semantic features of its HTML output."""

import argparse
import hashlib
from pathlib import Path
import re
import shutil
import subprocess
import sys

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "tex_to_accessible_html_converter"))
from mathml_validation import validate_mathml_structure  # noqa: E402

parser = argparse.ArgumentParser()
parser.add_argument("--engine", choices=["latex", "lualatex", "xelatex"], required=True)
args = parser.parse_args()
work = root / "build/tex-integration" / args.engine
work.mkdir(parents=True, exist_ok=True)
source = work / "integration.tex"
shutil.copyfile(root / "tests/fixtures/integration.tex", source)
before = hashlib.sha256(source.read_bytes()).digest()
cli = root / "tex_to_accessible_html_converter/tex_to_accessible_html_cli.py"
command = [sys.executable, str(cli), str(source), "--engine", args.engine,
           "--tex-distribution", "texlive", "--timeout", "180", "--keep", "all"]
result = subprocess.run(command, capture_output=True, text=True, timeout=240)
(work / "cli.log").write_text(result.stdout + result.stderr, encoding="utf-8")
if hashlib.sha256(source.read_bytes()).digest() != before:
    raise SystemExit("Conversion modified the source document.")
if result.returncode:
    raise SystemExit(result.stdout + result.stderr)
html = source.with_suffix(".html").read_text(encoding="utf-8")
errors = validate_mathml_structure(html)
for pattern in [r'<math\b', r'<mfrac\b', r'<msup\b', r'<msub\b',
                r'<msqrt\b', r'http://www.w3.org/1998/Math/MathML',
                r'<main\b', r'<a\b[^>]*href=["\']#', 'Проверка']:
    if not re.search(pattern, html, re.IGNORECASE):
        errors.append(f"Missing output feature: {pattern}")
if re.search(r'>\s*\?\?\s*<', html):
    errors.append("Unresolved reference in HTML.")
if errors:
    raise SystemExit("\n".join(errors))
invalid = work / "invalid.tex"
invalid.write_text(r"\documentclass{article}\begin{document}\undefinedCICommand\end{document}",
                   encoding="utf-8")
failed = subprocess.run([*command[:2], str(invalid), *command[3:]],
                        capture_output=True, text=True, timeout=240)
(work / "invalid-cli.log").write_text(failed.stdout + failed.stderr, encoding="utf-8")
if failed.returncode != 1 or invalid.with_suffix(".html").exists():
    raise SystemExit("Invalid TeX must fail without publishing HTML.")
print(f"Real {args.engine} conversion and error handling passed.")

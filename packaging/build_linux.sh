#!/usr/bin/env bash
# Native Linux build; Windows packaging remains in build_installer.ps1.
set -euo pipefail
repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"
if [[ "$(uname -s)" != Linux ]]; then
    echo 'Build this distribution on Linux.' >&2
    exit 1
fi
python_bin="${PYTHON:-python3}"
"$python_bin" -c 'import PyInstaller, pytest, wx'
"$python_bin" packaging/compile_translations.py
if [[ "${SKIP_TESTS:-0}" != 1 ]]; then
    "$python_bin" -m pytest -q
fi
# Use the same spec to avoid divergent GUI/CLI dependency lists.
"$python_bin" -m PyInstaller --noconfirm --clean \
    --distpath dist/linux --workpath build/linux packaging/tex_to_accessible_html.spec
bundle=dist/linux/TeXToAccessibleHTML
cp dist/linux/TeXToAccessibleHTMLCLI "$bundle/"
mkdir -p "$bundle/docs"
cp LICENSE docs/README.html docs/README_RU.html "$bundle/docs/"
"$bundle/TeXToAccessibleHTMLCLI" --help
test -f "$bundle/_internal/locales/ru/LC_MESSAGES/tex_to_accessible_html.mo"
archive="TeXToAccessibleHTML-linux-$(uname -m).tar.gz"
mkdir -p dist/linux/release
tar -czf "dist/linux/release/$archive" -C dist/linux TeXToAccessibleHTML
(cd dist/linux/release && sha256sum "$archive" > SHA256SUMS-linux.txt)
printf 'Linux distribution: %s/dist/linux/release/%s\n' "$repo_root" "$archive"

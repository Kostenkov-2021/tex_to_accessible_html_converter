#!/usr/bin/env bash
# Check an exported release in a disposable runtime container as an ordinary user.
set -euo pipefail
release_dir="${1:?Pass the directory containing the archive and checksums}"
fixture="${2:?Pass the integration TeX fixture}"
work_dir="$(mktemp -d)"
trap 'rm -rf -- "$work_dir"' EXIT
(cd "$release_dir" && sha256sum -c SHA256SUMS-linux.txt)
tar -xzf "$release_dir/TeXToAccessibleHTML-linux-x86_64.tar.gz" -C "$work_dir"
bundle="$work_dir/TeXToAccessibleHTML"
bash "$(dirname -- "${BASH_SOURCE[0]}")/smoke_linux_gui.sh" "$bundle/TeXToAccessibleHTML"
for engine in latex lualatex xelatex; do
    "$bundle/TeXToAccessibleHTMLCLI" "$fixture" --engine "$engine" \
        --tex-distribution texlive --keep logs -o "$work_dir/$engine"
    html="$work_dir/$engine/integration.html"
    for tag in math mfrac msup msub msqrt main; do
        grep -Eq "<$tag([[:space:]>])" "$html"
    done
    grep -q 'Проверка' "$html"
    echo "Archived CLI: $engine conversion and output checks passed."
done

#!/usr/bin/env bash
# LuaTeX does not create missing legacy T2A metrics automatically. Let LaTeX
# prepare exactly the fonts used by the fixture, in the current user's TeX cache.
set -euo pipefail
fixture="$(realpath -- "${1:?Pass the integration TeX fixture}")"
work_dir="$(mktemp -d)"
trap 'rm -rf -- "$work_dir"' EXIT
if ! latex -interaction=nonstopmode -halt-on-error \
    -output-directory="$work_dir" "$fixture" >"$work_dir/latex.stdout.log" 2>&1; then
    cat "$work_dir/latex.stdout.log" >&2
    exit 1
fi
echo 'Legacy Cyrillic font metrics prepared for the integration fixture.'

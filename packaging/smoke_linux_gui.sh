#!/usr/bin/env bash
set -euo pipefail
gui="${1:?Pass the packaged GUI executable}"
log_file="$(mktemp)"
trap 'rm -f -- "$log_file"' EXIT
status=0
xvfb-run -a timeout --kill-after=5s 10s "$gui" >"$log_file" 2>&1 || status=$?
cat "$log_file"
if [[ "$status" != 124 ]]; then
    echo "GUI exited before the smoke test completed (status $status)." >&2
    exit 1
fi
echo 'Packaged GUI stayed running under Xvfb for 10 seconds.'

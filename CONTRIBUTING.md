# Contributing

Thank you for your interest in the project. Open an issue before a large change and describe the problem, expected behavior, and proposed verification.

## Local setup

Python 3.10 or newer is required. Real conversion runs also require TeX Live or MiKTeX with `make4ht` and TeX4ht.

```powershell
cd .\tex_to_accessible_html_converter
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install pytest wxPython
python -m pytest -q
```

The application targets Windows. Pull requests must preserve Windows process management, path handling, and accessibility behavior.

## Pull requests

- Add or update tests when behavior changes.
- Keep English as the source language, update the Russian `.po` catalog, and compile its `.mo` file after changing user-facing text.
- Keep the GUI and CLI thin; reusable behavior belongs in the shared conversion modules.
- Do not commit `conversion_runs`, TeX intermediate files, logs, or local environments.
- Never modify the user's original `.tex` file during conversion.
- Include a minimal source example for MathML changes.
- Run `python -m pytest -q` before submitting.

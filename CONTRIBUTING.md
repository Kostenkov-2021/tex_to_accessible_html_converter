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

## GitHub Actions

- **Tests** runs Windows unit tests on Python 3.10, 3.12 and 3.14.
- **Quality** checks Python errors with Ruff and validates workflow syntax with actionlint.
- **Localization** checks Russian catalog syntax, missing translations, format fields,
  deterministic compilation and localization tests.
- **Build Windows** builds and tests the GUI, CLI and Inno Setup installer for relevant
  pull requests or manual runs. Download `windows-distribution` from the run's artifacts
  for the portable ZIP, installer and SHA-256 checksums.
- **TeX integration** runs manually or weekly with TeX Live and all three engines.
  It checks MathML features, Cyrillic text, links, source preservation and failed conversion.
  HTML and diagnostic artifacts are retained for seven days.
- **CodeQL** analyzes Python and Actions on pushes, pull requests and weekly.
- **Dependency review** rejects high/critical vulnerable dependency additions in pull requests.
  Dependabot proposes weekly updates for Python dependencies and Actions.

To prepare a release, update the version in both the application's `pyproject.toml`
and `packaging/installer.iss`, then push the matching `vX.Y.Z` tag. Alternatively,
run **Draft release** manually with an existing tag. The workflow builds the tagged
commit and creates a draft containing the same Windows assets; publish it after review.
An existing release for that tag must be handled explicitly rather than overwritten.

Scheduled and manually dispatched workflows must be present on the default branch.
Enable the dependency graph for dependency review, and use the advanced CodeQL setup
with this workflow rather than a duplicate default setup. Private repositories may
require GitHub Code Security for these security checks.

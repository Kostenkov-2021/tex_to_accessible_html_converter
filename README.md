# TeX to Accessible HTML Converter

Russian source documentation is available in [README_RU.md](README_RU.md). 

A Windows application that converts LaTeX documents to HTML5 with Presentation MathML. It provides an accessible graphical interface and a command-line interface for automation. Generated formulas remain visual while also being available to screen readers, Braille output, and MathCAT where supported.

> [!IMPORTANT]
> The project is in alpha. Structural MathML validation cannot guarantee mathematical equivalence or correct speech output for every formula. TeX files can execute powerful commands; process untrusted documents only in an isolated environment.

## Features

- accessible wxPython graphical interface;
- batch conversion of individual `.tex` files or every `.tex` file in a folder;
- TeX Live and MiKTeX support;
- `latex`, `lualatex`, and `xelatex` engines;
- standard and draft UI modes (both currently use the complete TeX pass set to preserve references and the table of contents);
- embedded CSS and explicit MathML namespaces;
- MathML structure and common fidelity checks before replacing an existing result;
- time limits and four artifact-retention choices: HTML only, logs, temporary files, or logs and temporary files;
- isolated source staging: the original document is never modified;
- narrowly scoped compatibility changes applied only to the staged copy, including safe MathML relations, reference keys, prime superscripts, `multline`, and `\cfrac` handling.

> [!WARNING]
> Program logs and temporary files can occupy a large amount of disk space. Keep them only when investigating conversion errors.

## Requirements

- Python 3.10 or newer;
- wxPython;
- TeX Live or MiKTeX with `make4ht`, TeX4ht, and packages required by the source document.

Install wxPython in the Python environment used to start the application:

```powershell
python -m pip install wxPython
```

## Run

```powershell
cd .\tex_to_accessible_html_converter
python .\tex_to_accessible_html_gui.py
```

With `uv`, ensure wxPython is available in the selected environment and run:

```powershell
uv run python .\tex_to_accessible_html_gui.py
```

Add files with **Add .tex**, or use **Add folder** to add all `.tex` files directly in one folder. Choose the output location, conversion options, and **Files to keep**, then select **Convert**. Folder selection is non-recursive. By default, only HTML is written next to each source document.

## Command line

The CLI does not import wxPython, so it is suitable for servers and automation:

```text
python tex_to_accessible_html_cli.py INPUT [INPUT ...] [--recursive]
  [-o OUTPUT_DIR] [--engine latex|lualatex|xelatex]
  [--mode default|draft] [--tex-distribution auto|texlive|miktex]
  [--timeout SECONDS] [--keep html|logs|temporary|all]
```

Each input may be a file or directory. Directories are non-recursive unless `--recursive` is supplied. Exit status is `0` on complete success, `1` if any conversion fails, and `2` for invalid arguments or when no TeX files are found.

Example:

```powershell
python .\tex_to_accessible_html_cli.py .\lectures --recursive -o .\html --keep logs
```

## How it works

For each document, `converter.py` creates an isolated build directory and stages the source tree without changing the original. `tex_compatibility.py` applies narrowly scoped TeX4ht compatibility changes to the staged copy. `conversion_process.py` runs `make4ht` with the chosen TeX engine and enforces the timeout. The generated HTML is then normalized; `mathml_fidelity.py` repairs known TeX4ht MathML distortions, and `mathml_validation.py` rejects structurally invalid MathML. Only a validated result replaces the destination HTML. Logs contain diagnostic output; temporary retention copies the complete isolated build tree into a timestamp-unique `*.html.temporary/run-*` directory. Logs use `*.html.logs/run-*`.

The GUI is implemented by `tex_to_accessible_html_gui.py`; `tex_to_accessible_html_cli.py` calls the same conversion pipeline. Thus both interfaces use identical conversion, repair, validation, and safety behavior.

Select **Open documentation** or press **F1** anywhere in the main window to open the local HTML documentation for the current interface language in the default browser. This works offline in both the portable distribution and the installed application. Markdown documentation remains in the source repository and is not included in binary distributions.

## Interface languages

English is the primary documentation and source/fallback interface language. Russian is loaded through GNU gettext from `locales/ru/LC_MESSAGES/tex_to_accessible_html.mo`. Use the **Language** selector in the application to switch immediately between English and Russian. The selection is saved in the current user's application-data directory.

The binary distribution includes the corresponding English and Russian HTML documents under `docs`; Markdown files remain in the source repository.

For managed or portable launches, the language can also be forced before startup; this environment variable takes precedence over the saved preference:

```powershell
$env:TEX_ACCESSIBLE_HTML_LANGUAGE = "ru"  # or "en"
python .\tex_to_accessible_html_gui.py
```

External TeX tools may continue to produce messages in their own configured language.

After editing the `.po` file, rebuild the binary catalog with the repository automation:

```powershell
python ..\packaging\compile_translations.py
```

## Project structure

- `tex_to_accessible_html_gui.py` — accessible graphical entry point;
- `tex_to_accessible_html_cli.py` — command-line entry point;
- `converter.py` — conversion pipeline used by the GUI;
- `conversion_process.py` — bounded subprocess execution and log capture;
- `tex_compatibility.py` — TeX4ht MathML configuration and isolated compatibility helpers;
- `mathml_fidelity.py` — targeted MathML fidelity repairs;
- `mathml_validation.py` — structural MathML validation;
- `localization.py` and `locales/` — GNU gettext language selection and translation catalogs;
- `tests/test_*.py` — unit tests that do not require a TeX installation.

## Development

From the repository root:

```powershell
.\tex_to_accessible_html_converter\.venv\Scripts\python.exe -m pytest -q
```

Or create a fresh environment as described in [CONTRIBUTING.md](CONTRIBUTING.md). Real conversion results vary with TeX distribution versions, installed packages, and user configuration.


## Build the Windows installer

Install the development tools and [Inno Setup](https://jrsoftware.org/isdl.php), then run from the repository root:

```powershell
uv pip install --python .\tex_to_accessible_html_converter\.venv\Scripts\python.exe `
  -r .\packaging\requirements-build.txt
.\packaging\build_installer.ps1
```

The standalone GUI is written to `dist\TeXToAccessibleHTML`, the standalone
`TeXToAccessibleHTMLCLI.exe` to `dist`, and the installer to `dist\installer`. The standalone directory and installed application
include English and Russian documentation under `docs`. TeX Live or MiKTeX remains
an external runtime requirement because TeX package sets are managed by those distributions.

## Security and license

See [SECURITY.md](SECURITY.md) before processing untrusted documents. The project is distributed under the [MIT License](LICENSE).

## Feedback and contributing

Report bugs and request features in [GitHub Issues](https://github.com/Kostenkov-2021/tex_to_accessible_html_converter/issues). Contributions are welcome; read [CONTRIBUTING.md](CONTRIBUTING.md) before opening a pull request. Include a minimal `.tex` example, the selected distribution/engine, and retained logs when reporting a conversion error. Do not publish confidential source documents or logs.

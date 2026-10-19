# Linux / Линукс

## English

Windows and Linux have separate distributions and share the conversion engine.
Windows continues to use the portable ZIP and Inno Setup installer. Linux uses
`TeXToAccessibleHTML-linux-x86_64.tar.gz`, built natively on Ubuntu 24.04 x86_64.
The Linux archive includes GUI, CLI, translations and offline HTML documentation.
It needs system GTK libraries and an installed TeX distribution; it is not a
universal binary for every Linux distribution. PyInstaller does not bundle glibc.
Older systems should run from source. Other architectures require a native build.

### Run from source (Ubuntu 24.04 / Debian with Python >= 3.10 and wxPython >= 4.2)

From the repository root:

```bash
sudo apt-get update
sudo apt-get install python3-wxgtk4.0 texlive-extra-utils texlive-latex-extra texlive-luatex texlive-xetex texlive-lang-cyrillic texlive-fonts-recommended cm-super
/usr/bin/python3 tex_to_accessible_html_converter/tex_to_accessible_html_gui.py
```

For a server, wxPython is optional. The CLI uses only Python's standard library:

```bash
python3 tex_to_accessible_html_converter/tex_to_accessible_html_cli.py ./lectures --recursive -o ./html --tex-distribution texlive --keep logs
```

TeX Live with `make4ht` on PATH is the Linux reference configuration. Source
documents may require additional TeX packages. MiKTeX can be selected if its tools
are on PATH; automatic discovery of Windows installation folders remains a
Windows convenience. No shell profile is loaded by the application.

### Run the Linux archive

On a minimal Ubuntu 24.04 installation, install the GUI runtime libraries too:

```bash
sudo apt-get install libgtk-3-0t64 libgl1 librsvg2-common shared-mime-info
```

```bash
sha256sum -c SHA256SUMS-linux.txt
tar -xzf TeXToAccessibleHTML-linux-x86_64.tar.gz
./TeXToAccessibleHTML/TeXToAccessibleHTML
./TeXToAccessibleHTML/TeXToAccessibleHTMLCLI --help
```

Use a graphical desktop for the GUI.  F1 opens the bundled HTML help.

Language settings are stored in
`${XDG_CONFIG_HOME:-$HOME/.config}/TeXToAccessibleHTML/settings.json`.
Relative XDG_CONFIG_HOME values are ignored. `TEX_ACCESSIBLE_HTML_LANGUAGE=ru`
or `en` overrides the saved setting. Windows retains its AppData settings path.

### Build on Linux

```bash
sudo apt-get install python3-venv python3-wxgtk4.0 libpython3.12
/usr/bin/python3 -m venv --system-site-packages .venv-linux
.venv-linux/bin/python -m pip install 'pyinstaller>=6.22' 'pytest>=8'
PYTHON=.venv-linux/bin/python bash packaging/build_linux.sh
```

The system Python must match the installed wxGTK package. This avoids compiling
wxPython from source. Results are in `dist/linux/release/`, separate from Windows
outputs. The build runs unit tests, compiles translations, packages GUI and CLI,
copies documentation and creates the tar archive and SHA-256 checksum. CI also
checks GUI startup under Xvfb and real TeX conversions for all three engines.
The release workflow attaches both platforms to one draft release.

## Русский

Для Linux создаётся отдельный архив `TeXToAccessibleHTML-linux-x86_64.tar.gz`;
Windows сохраняет ZIP и установщик Inno Setup. Общее ядро обеспечивает одинаковые
проверки HTML и MathML. Linux-сборка рассчитана на Ubuntu 24.04 x86_64;
совместимость с другими дистрибутивами требует проверки библиотек GTK и glibc.
Для старых систем используйте запуск из исходников командами выше.

Для GUI установите системный `python3-wxgtk4.0` версии не ниже 4.2 и запускайте
его через `/usr/bin/python3`. Для CLI wxPython не требуется. TeX Live и пакеты
исходного документа устанавливаются отдельно. Примеры установки, запуска,
проверки контрольной суммы и сборки приведены выше.

Настройки языка сохраняются в каталоге XDG, по умолчанию
`~/.config/TeXToAccessibleHTML/settings.json`. Windows продолжает использовать
AppData. По тайм-ауту Linux останавливает отдельную группу процессов, включая
дочерние TeX-процессы; Windows использует прежний `taskkill /T /F`.


## Docker checks / Проверка в Docker

From the repository root / Из корня репозитория:

```bash
# On Windows or when local cache folders cannot be read, stage a small context:
python packaging/prepare_linux_context.py
# Unit tests, real TeX integration, native packaging, clean runtime GUI/CLI checks
docker build --target verify -f build/linux-docker-context/packaging/Dockerfile.linux -t tex-accessible-linux:verified build/linux-docker-context
```

For a clean Linux checkout, the repository itself can be used as the context:

```bash
# Unit tests, real TeX integration, native packaging, clean runtime GUI/CLI checks
docker build --target verify -f packaging/Dockerfile.linux -t tex-accessible-linux:verified .
# Keep build tools and the release archive in a separately tagged image
docker build --target build -f packaging/Dockerfile.linux -t tex-accessible-linux:build .
docker create --name tex-accessible-linux-export tex-accessible-linux:build
docker cp tex-accessible-linux-export:/app/dist/linux/release ./dist/linux-container-release
docker rm tex-accessible-linux-export
docker run --rm tex-accessible-linux:verified --help
```

The `test`, `build`, `runtime` and `verify` stages use Ubuntu 24.04. `verify`
starts the packaged GUI under Xvfb for 10 seconds and converts the fixture with
the packaged CLI using all three engines. The runtime stage does not copy the
build environment or application source modules. Docker checks do not require a
host TeX installation. The build stage reuses the successful unit-test layer
instead of running the same tests twice (`SKIP_TESTS=1` for that step only).
The Docker context includes only required sources, excluding local environments
and conversion archives.

### Debian 13 (trixie)

The same Dockerfile supports Debian through build arguments, without a separate
copy of the tests or packaging steps. Debian 13 uses Python 3.13 and its matching
system wxPython package:

```bash
python packaging/prepare_linux_context.py
docker build --build-arg LINUX_IMAGE=debian:trixie-slim --build-arg PYTHON_LIBRARY=libpython3.13 --target verify -f build/linux-docker-context/packaging/Dockerfile.linux -t tex-accessible-debian:verified build/linux-docker-context
```

For a native source build on Debian 13, use `libpython3.13` in place of
`libpython3.12` in the installation command above. Keep archives built on Debian
in a separate output directory from the Ubuntu release: their filenames match,
but their runtime libraries and minimum glibc requirements can differ.

Export just the Debian archive and checksum using cached build layers:

```bash
docker build --build-arg LINUX_IMAGE=debian:trixie-slim --build-arg PYTHON_LIBRARY=libpython3.13 --target release --output type=local,dest=dist/debian-container-release -f packaging/Dockerfile.linux build/linux-docker-context
```


В Debian 13 проверены исходники, сборка и готовые архивы Ubuntu и Debian.
Все 232 модульных теста прошли; GUI и конвертация тремя движками работают.


Dependency installation happens before source copying, so source edits reuse
installed packages. Dockerfile changes do not invalidate the application copy.
The verification stage prepares legacy Cyrillic font metrics in TeX's shared
system cache and then runs LuaLaTeX conversion as UID 1000. It does not depend
on a private root font cache. On a new desktop TeX installation, legacy T2A
documents may need font metrics generated first (for example,
`mktextfm larm1000` for that missing font); use the font name reported by TeX.
The converter preserves the distribution's cache settings.

The LuaLaTeX integration job prepares the fixture's legacy T2A font metrics
explicitly with `bash packaging/prepare_tex_fonts.sh tests/fixtures/integration.tex`.
This uses LaTeX's automatic metric generation in the same user's TeX cache;
the temporary document outputs are removed. Docker performs the same preparation
and runs LuaLaTeX integration first, so a preceding conversion cannot silently
supply its font metrics. No additional font bundle or fixed list of font sizes
is needed; preparation follows the fixture when it changes.

Стадия `verify` проверяет готовые исполняемые файлы в отдельном окружении без
копирования среды сборки. GUI запускается под Xvfb; CLI преобразует пример тремя
движками. Локальная установка TeX на Windows для этих проверок не нужна.



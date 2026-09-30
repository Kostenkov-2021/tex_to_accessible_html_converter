[CmdletBinding()]
param(
    [string]$Python,
    [string]$Iscc,
    [switch]$SkipTests
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$projectRoot = Join-Path $repoRoot "tex_to_accessible_html_converter"
$distRoot = Join-Path $repoRoot "dist"
$buildRoot = Join-Path $repoRoot "build"

if (-not $Python) {
    $Python = Join-Path $projectRoot ".venv\Scripts\python.exe"
}
if (-not (Test-Path -LiteralPath $Python)) {
    throw "Python was not found at '$Python'. Pass -Python with a Python executable containing the packages from packaging\requirements-build.txt."
}

& $Python -c "import PyInstaller, pytest, wx"
if ($LASTEXITCODE -ne 0) {
    throw "Build dependencies are missing. Run: '$Python' -m pip install -r packaging\requirements-build.txt"
}

& $Python (Join-Path $PSScriptRoot "compile_translations.py")
if ($LASTEXITCODE -ne 0) { throw "gettext catalog compilation failed." }

if (-not $SkipTests) {
    New-Item -ItemType Directory -Path $buildRoot -Force | Out-Null
    $testFiles = Get-ChildItem -LiteralPath (Join-Path $projectRoot "tests") -Filter "test_*.py" -File |
        Sort-Object Name |
        Select-Object -ExpandProperty FullName
    if (-not $testFiles) { throw "No test_*.py files were found in '$projectRoot'." }
    $pytestTemp = Join-Path $buildRoot ("pytest-temp-" + [guid]::NewGuid().ToString("N"))
    & $Python -m pytest -q $testFiles --basetemp $pytestTemp
    if ($LASTEXITCODE -ne 0) { throw "Tests failed." }
}

& $Python -m PyInstaller `
    --noconfirm `
    --clean `
    --distpath $distRoot `
    --workpath $buildRoot `
    (Join-Path $PSScriptRoot "tex_to_accessible_html.spec")
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed." }

$cliExecutable = Join-Path $distRoot "TeXToAccessibleHTMLCLI.exe"
if (-not (Test-Path -LiteralPath $cliExecutable)) {
    throw "The command-line executable was not created: '$cliExecutable'."
}
Copy-Item -LiteralPath $cliExecutable -Destination (Join-Path $distRoot "TeXToAccessibleHTML\TeXToAccessibleHTMLCLI.exe") -Force

$documentationDir = Join-Path $distRoot "TeXToAccessibleHTML\docs"
New-Item -ItemType Directory -Path $documentationDir -Force | Out-Null
Copy-Item -LiteralPath (Join-Path $repoRoot "LICENSE") -Destination $documentationDir -Force
Copy-Item -LiteralPath (Join-Path $repoRoot "docs\README.html") -Destination $documentationDir -Force
Copy-Item -LiteralPath (Join-Path $repoRoot "docs\README_RU.html") -Destination $documentationDir -Force

if (-not $Iscc) {
    $isccCandidates = @(
        (Join-Path ${env:ProgramFiles} "Inno Setup 7\ISCC.exe"),
        (Join-Path ${env:ProgramFiles(x86)} "Inno Setup 7\ISCC.exe"),
        (Join-Path ${env:ProgramFiles(x86)} "Inno Setup 6\ISCC.exe"),
        (Join-Path ${env:LOCALAPPDATA} "Programs\Inno Setup 7\ISCC.exe"),
        (Join-Path ${env:LOCALAPPDATA} "Programs\Inno Setup 6\ISCC.exe")
    )
    $Iscc = $isccCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
}
if (-not $Iscc -or -not (Test-Path -LiteralPath $Iscc)) {
    throw "ISCC.exe was not found. Install Inno Setup or pass -Iscc with its full path."
}

& $Iscc (Join-Path $PSScriptRoot "installer.iss")
if ($LASTEXITCODE -ne 0) { throw "Inno Setup failed." }

$installer = Get-ChildItem -LiteralPath (Join-Path $distRoot "installer") -Filter "*.exe" |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1
Write-Host "Installer created: $($installer.FullName)"

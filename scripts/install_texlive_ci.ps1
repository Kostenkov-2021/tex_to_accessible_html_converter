# Install only the TeX Live collections needed by the integration fixtures.
[CmdletBinding()]
param(
    [string]$Repository = 'https://mirror.ctan.org/systems/texlive/tlnet'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
if (-not $IsWindows -or -not $env:RUNNER_TEMP -or -not $env:GITHUB_PATH) {
    throw 'This installer requires a Windows GitHub Actions runner.'
}

$work = Join-Path $env:RUNNER_TEMP ('texlive-installer-' + [guid]::NewGuid())
$texRoot = Join-Path $env:RUNNER_TEMP 'texlive'
if (Test-Path -LiteralPath $texRoot) {
    throw "Refusing to overwrite an existing TeX Live installation: $texRoot"
}
New-Item -ItemType Directory -Path $work | Out-Null
$archive = Join-Path $work 'install-tl.zip'
Invoke-WebRequest -Uri "$Repository/install-tl.zip" -OutFile $archive -TimeoutSec 180
Expand-Archive -LiteralPath $archive -DestinationPath $work
$installers = @(Get-ChildItem -LiteralPath $work -Recurse -Filter 'install-tl-windows.bat')
if ($installers.Count -ne 1) {
    throw 'Expected exactly one TeX Live Windows installer in the archive.'
}
$profile = Join-Path $work 'texlive.profile'
$portableRoot = $texRoot.Replace('\', '/')
@"
selected_scheme scheme-custom
TEXDIR $portableRoot
TEXMFLOCAL $portableRoot/texmf-local
TEXMFSYSCONFIG $portableRoot/texmf-config
TEXMFSYSVAR $portableRoot/texmf-var
collection-basic 1
collection-latex 1
collection-latexrecommended 1
collection-latexextra 1
collection-luatex 1
collection-xetex 1
collection-langcyrillic 1
collection-fontsrecommended 1
collection-plaingeneric 1
instopt_adjustpath 0
tlpdbopt_desktop_integration 0
tlpdbopt_file_assocs 0
tlpdbopt_install_docfiles 0
tlpdbopt_install_srcfiles 0
"@ | Set-Content -LiteralPath $profile -Encoding ascii

& $installers[0].FullName '-no-gui' '-profile' $profile '-repository' $Repository
if ($LASTEXITCODE -ne 0) { throw "TeX Live installation failed ($LASTEXITCODE)." }
$bin = Join-Path $texRoot 'bin/windows'
$tlmgr = Join-Path $bin 'tlmgr.bat'
# The Windows installer wrapper can return zero even when install-tl stops early.
if (-not (Test-Path -LiteralPath $tlmgr -PathType Leaf) -or
    -not (Test-Path -LiteralPath (Join-Path $texRoot 'tlpkg/texlive.tlpdb') -PathType Leaf)) {
    throw "TeX Live installation did not complete; inspect the installer output above. Installer files: $work"
}
$env:PATH = "$bin;$env:PATH"
# TeX4ht and scalable Cyrillic fonts are explicit runtime requirements.
& $tlmgr install tex4ht make4ht cm-super
if ($LASTEXITCODE -ne 0) { throw "TeX Live package installation failed ($LASTEXITCODE)." }
$bin | Out-File -LiteralPath $env:GITHUB_PATH -Append -Encoding utf8

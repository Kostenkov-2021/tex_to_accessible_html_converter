# Install only the TeX Live collections needed by the integration fixtures.
[CmdletBinding()]
param(
    [string[]]$Repository = @(
        'https://mirrors.ibiblio.org/pub/mirrors/CTAN/systems/texlive/tlnet',
        'https://mirror.math.princeton.edu/pub/CTAN/systems/texlive/tlnet'
    )
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
$selectedRepository = $null
$installer = $null
$mirrorNumber = 0
foreach ($mirror in $Repository) {
    $mirrorNumber++
    for ($attempt = 1; $attempt -le 2; $attempt++) {
        $download = Join-Path $work "m$mirrorNumber-try$attempt"
        New-Item -ItemType Directory -Path $download | Out-Null
        $archive = Join-Path $download 'install-tl.zip'
        try {
            Write-Host "Downloading TeX Live installer from $mirror (attempt $attempt/2)."
            Invoke-WebRequest -Uri "$($mirror.TrimEnd('/'))/install-tl.zip" -OutFile $archive -TimeoutSec 180
            # Reject HTML challenges, truncated ZIPs and unexpected archive layouts.
            Expand-Archive -LiteralPath $archive -DestinationPath (Join-Path $download 'unpacked')
            $installers = @(Get-ChildItem -LiteralPath (Join-Path $download 'unpacked') -Recurse -Filter 'install-tl-windows.bat')
            if ($installers.Count -ne 1) {
                throw 'Expected exactly one TeX Live Windows installer in the archive.'
            }
            $installer = $installers[0].FullName
            $selectedRepository = $mirror
            break
        } catch {
            # Avoid printing a potentially huge HTML response body into CI logs.
            Write-Warning "Could not download and unpack a TeX Live installer from $mirror (attempt $attempt/2; $($_.Exception.GetType().Name))."
            if ($attempt -lt 2) { Start-Sleep -Seconds 2 }
        }
    }
    if ($selectedRepository) { break }
}
if (-not $selectedRepository) {
    throw "Failed to obtain a valid TeX Live installer from all configured mirrors. Download diagnostics: $work"
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

Write-Host "Installing TeX Live from $selectedRepository."
& $installer '-no-gui' '-profile' $profile '-repository' $selectedRepository
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
& $tlmgr '--repository' $selectedRepository install tex4ht make4ht cm-super
if ($LASTEXITCODE -ne 0) { throw "TeX Live package installation failed ($LASTEXITCODE)." }
$bin | Out-File -LiteralPath $env:GITHUB_PATH -Append -Encoding utf8

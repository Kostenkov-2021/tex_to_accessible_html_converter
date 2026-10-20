# Exercise early installer failures without downloading or installing TeX Live.
$ErrorActionPreference = 'Stop'
$installerScript = Join-Path $PSScriptRoot 'install_texlive_ci.ps1'
$testRoot = Join-Path ([System.IO.Path]::GetTempPath()) ('texlive-test-' + [guid]::NewGuid())
$previousTemp = $env:RUNNER_TEMP
$previousPathFile = $env:GITHUB_PATH
New-Item -ItemType Directory -Path $testRoot | Out-Null
try {
    $env:GITHUB_PATH = Join-Path $testRoot 'github-path'
    function Invoke-WebRequest { param($Uri, $OutFile, $TimeoutSec) }
    function Expand-Archive {
        param($LiteralPath, $DestinationPath)
        # Simulate the official wrapper returning success without an installation.
        $exitCode = if ($DestinationPath -like '*case-0*') { 0 } else { 1 }
        Set-Content -LiteralPath (Join-Path $DestinationPath 'install-tl-windows.bat') `
            -Value "@exit /b $exitCode" -Encoding ascii
    }
    foreach ($fakeExitCode in @(0, 1)) {
        $env:RUNNER_TEMP = Join-Path $testRoot "case-$fakeExitCode"
        New-Item -ItemType Directory -Path $env:RUNNER_TEMP | Out-Null
        $caught = $null
        try { & $installerScript } catch { $caught = $_.Exception.Message }
        $expected = if ($fakeExitCode -eq 0) { 'did not complete' } else { 'installation failed' }
        if (-not $caught -or -not $caught.Contains($expected)) {
            throw "Expected '$expected', got '$caught'."
        }
        if (Test-Path -LiteralPath $env:GITHUB_PATH) {
            throw 'An unsuccessful installation must not publish its PATH.'
        }
        $profile = Get-ChildItem -LiteralPath $env:RUNNER_TEMP -Recurse -Filter texlive.profile
        $text = Get-Content -LiteralPath $profile.FullName -Raw
        if ($text -match '(?m)^instopt_(desktop_integration|file_assocs) ' -or
            $text -notmatch '(?m)^tlpdbopt_desktop_integration 0' -or
            $text -notmatch '(?m)^tlpdbopt_file_assocs 0') {
            throw 'Incorrect Windows profile option names.'
        }
    }
    Write-Host 'TeX Live installer failure checks passed.'
} finally {
    $env:RUNNER_TEMP = $previousTemp
    $env:GITHUB_PATH = $previousPathFile
    # Keep test artifacts for diagnostics; the runner cleans its temporary directory.
}
# The final simulated installer deliberately returned 1; report test success to CI.
exit 0

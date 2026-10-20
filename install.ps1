# Sets up the kaomoji picker on this PC: a Python environment in .venv, the packages, the
# meaning model, optionally a Startup shortcut, and then starts it. Safe to run again to
# repair or update. Double-click install.cmd rather than running this directly; it gets
# past PowerShell's script policy.
#   -Startup / -NoStartup   answer the "start with Windows?" question up front
param([switch]$Startup, [switch]$NoStartup)
# Not 'Stop': Windows PowerShell turns any stderr line of pip or python into a terminating
# error. Each native call checks its exit code instead.
$ErrorActionPreference = 'Continue'
Set-Location $PSScriptRoot

function Find-Python {
    # The py launcher first (python.org installs), then python on PATH. The Microsoft Store
    # stub called python prints nothing, so it fails the version check and is skipped.
    foreach ($candidate in @(@('py', '-3'), @('python'))) {
        if (-not (Get-Command $candidate[0] -ErrorAction SilentlyContinue)) { continue }
        $extra = @($candidate | Select-Object -Skip 1)
        try {
            $ok = & $candidate[0] @extra -c "import sys; print(sys.version_info >= (3, 10))" 2>$null
        } catch { $ok = $null }
        if ($ok -eq 'True') { return , $candidate }
    }
    return $null
}

Write-Host "1/4  Looking for Python 3.10 or newer..."
$venvPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
$venvPythonw = Join-Path $PSScriptRoot '.venv\Scripts\pythonw.exe'
if (-not (Test-Path $venvPython)) {
    $python = Find-Python
    if (-not $python) {
        Write-Host ""
        Write-Host "No Python 3.10+ found. Install it, then run install.cmd again:" -ForegroundColor Yellow
        Write-Host "  winget install Python.Python.3.12" -ForegroundColor Yellow
        Write-Host "  (or python.org/downloads, with 'Add python.exe to PATH' ticked)" -ForegroundColor Yellow
        exit 1
    }
    $extra = @($python | Select-Object -Skip 1)
    & $python[0] @extra -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw "Couldn't create the Python environment in .venv" }
}

Write-Host "2/4  Installing the packages (first time: ~150 MB, a minute or two)..."
& $venvPython -m pip install --disable-pip-version-check --quiet --upgrade pip
& $venvPython -m pip install --disable-pip-version-check --quiet -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw "pip couldn't install the packages; see the messages above" }

Write-Host "3/4  Checking it works (first time: downloads the 116 MB meaning model)..."
$env:PYTHONIOENCODING = 'utf-8'
$check = & $venvPython kaomoji.py --suggest "wait, how does this work?" 2>$null
if ($LASTEXITCODE -ne 0 -or -not ($check -match '^moods: .+')) {
    throw "The check failed. Run '.venv\Scripts\python.exe kaomoji.py --suggest hello' to see why."
}
Write-Host "     $($check | Select-Object -First 1)"

Write-Host "4/4  Start with Windows?"
if (-not $Startup -and -not $NoStartup) {
    $answer = Read-Host "     Start the picker automatically when you log in? [Y/n]"
    $Startup = $answer -notmatch '^\s*n'
}
$link = Join-Path ([Environment]::GetFolderPath('Startup')) 'Kaomoji picker.lnk'
if ($Startup) {
    $shortcut = (New-Object -ComObject WScript.Shell).CreateShortcut($link)
    $shortcut.TargetPath = $venvPythonw
    $shortcut.Arguments = "`"$(Join-Path $PSScriptRoot 'kaomoji.py')`""
    $shortcut.WorkingDirectory = $PSScriptRoot
    $shortcut.Save()
    Write-Host "     Added $link (delete it to undo)"
} else {
    Write-Host "     Skipped. Start it with kaomoji.cmd when you want it."
}

$running = Get-CimInstance Win32_Process -Filter "Name='pythonw.exe' OR Name='python.exe'" |
    Where-Object { $_.CommandLine -match 'kaomoji\.py"?\s*$' }
if ($running) {
    Write-Host ""
    Write-Host "Done. It's already running: quit it from the tray icon and start kaomoji.cmd to load this version."
} else {
    Start-Process -FilePath $venvPythonw -ArgumentList "`"$(Join-Path $PSScriptRoot 'kaomoji.py')`"" -WorkingDirectory $PSScriptRoot
    Write-Host ""
    Write-Host "Done. It's running in the tray: press Ctrl+Alt+K in any text box."
}

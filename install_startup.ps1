# Makes the kaomoji picker start with Windows: a shortcut in shell:startup. Delete the .lnk to undo.
$pythonw = (Get-Command pythonw).Source
$script = Join-Path $PSScriptRoot 'kaomoji.py'
$link = Join-Path ([Environment]::GetFolderPath('Startup')) 'Kaomoji picker.lnk'
$shortcut = (New-Object -ComObject WScript.Shell).CreateShortcut($link)
$shortcut.TargetPath = $pythonw
$shortcut.Arguments = "`"$script`""
$shortcut.WorkingDirectory = $PSScriptRoot
$shortcut.Save()
"Added $link"

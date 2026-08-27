$ErrorActionPreference = "Stop"
$exe = Join-Path $PSScriptRoot "IzurenVideoManager.exe"
if (-not (Test-Path $exe)) {
    Add-Type -AssemblyName PresentationFramework
    [System.Windows.MessageBox]::Show("Run this installer from the same folder as IzurenVideoManager.exe.", "Installation failed")
    exit 1
}

$action = New-ScheduledTaskAction -Execute $exe -Argument "--background"
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew
Register-ScheduledTask -TaskName "Izuren Video Manager" -Action $action -Trigger $trigger -Settings $settings -Description "Checks for new IzurenTV videos and playlists" -Force | Out-Null

$shortcutCreated = $false
try {
    $desktop = [Environment]::GetFolderPath([Environment+SpecialFolder]::DesktopDirectory)
    if (-not [string]::IsNullOrWhiteSpace($desktop)) {
        $shell = New-Object -ComObject WScript.Shell
        $shortcutPath = Join-Path $desktop "Izuren Video Manager.lnk"
        $shortcut = $shell.CreateShortcut($shortcutPath)
        $shortcut.TargetPath = $exe
        $shortcut.WorkingDirectory = $PSScriptRoot
        $shortcut.Save()
        $shortcutCreated = $true
    }
} catch {
    $shortcutCreated = $false
}

Add-Type -AssemblyName PresentationFramework
if ($shortcutCreated) {
    [System.Windows.MessageBox]::Show("Auto-start and the desktop shortcut are ready.", "Installation complete")
} else {
    [System.Windows.MessageBox]::Show("Auto-start is ready. The shortcut could not be created; use the EXE in this folder.", "Installation complete")
}

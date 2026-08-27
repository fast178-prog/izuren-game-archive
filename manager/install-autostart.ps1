$ErrorActionPreference = "Stop"
$exe = Join-Path $PSScriptRoot "IzurenVideoManager.exe"
if (-not (Test-Path $exe)) {
    Add-Type -AssemblyName PresentationFramework
    [System.Windows.MessageBox]::Show("IzurenVideoManager.exe와 같은 폴더에서 실행해 주세요.", "설치 실패")
    exit 1
}

$action = New-ScheduledTaskAction -Execute $exe -Argument "--background"
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew
Register-ScheduledTask -TaskName "Izuren Video Manager" -Action $action -Trigger $trigger -Settings $settings -Description "이즈렌TV 새 영상 및 재생목록 자동 확인" -Force | Out-Null

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
    [System.Windows.MessageBox]::Show("자동 실행과 바탕화면 바로가기를 설정했습니다.", "설치 완료")
} else {
    [System.Windows.MessageBox]::Show("자동 실행을 설정했습니다. 바로가기는 만들지 못했으므로 현재 폴더의 EXE를 사용해 주세요.", "설치 완료")
}

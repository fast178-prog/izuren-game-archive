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

$shell = New-Object -ComObject WScript.Shell
$shortcutPath = Join-Path ([Environment]::GetFolderPath("Desktop")) "이즈렌 영상 등록 관리.lnk"
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $exe
$shortcut.WorkingDirectory = $PSScriptRoot
$shortcut.Save()

Add-Type -AssemblyName PresentationFramework
[System.Windows.MessageBox]::Show("자동 실행과 바탕화면 바로가기를 설정했습니다.", "설치 완료")

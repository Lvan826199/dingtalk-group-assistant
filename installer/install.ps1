param([switch]$RegisterOnly, [string]$Target = 'C:\qa-agent', [string]$Python = '')
$ErrorActionPreference = 'Stop'
$stage = '检测 Python'
try {
    if ($RegisterOnly) {
        $stage = '创建当前用户的开机计划任务'
        $pythonw = Join-Path (Split-Path $Python) 'pythonw.exe'
        if (-not (Test-Path $pythonw)) { throw '未找到同目录 pythonw.exe，请安装完整版 Python。' }
        $act = New-ScheduledTaskAction -Execute $pythonw -Argument ('"' + (Join-Path $Target 'agent.py') + '"') -WorkingDirectory $Target
        $trg1 = New-ScheduledTaskTrigger -Daily -At 09:00
        $trg2 = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
        $set = New-ScheduledTaskSettingsSet -Hidden -StartWhenAvailable -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew
        $principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited
        Register-ScheduledTask -TaskName 'QA-群消息助手' -Action $act -Trigger $trg1,$trg2 -Settings $set -Principal $principal -Description '群消息助手，监听时段由操作台设置' -Force | Out-Null
        exit 0
    }
    $launcher = Get-Command py.exe -ErrorAction SilentlyContinue
    if ($launcher) { & $launcher.Source -3 -I (Join-Path $PSScriptRoot 'install.py') --target $Target }
    else {
        $launcher = Get-Command python.exe -ErrorAction SilentlyContinue
        if (-not $launcher) { throw '未找到 Python 3.10+，请本人安装并加入 PATH 后重试。' }
        & $launcher.Source -I (Join-Path $PSScriptRoot 'install.py') --target $Target
    }
    exit $LASTEXITCODE
} catch {
    Write-Host ('安装未完成（' + $stage + '）：请检查 Python、目录权限和本人登录会话中的计划任务；不需要管理员权限。')
    exit 1
}

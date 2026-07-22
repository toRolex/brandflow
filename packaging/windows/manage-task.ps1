param(
    [string]$Action = "start"
)

$taskName = "brandflow-control-plane"
$wrapper = "D:\brandflow\tools\run_control_plane.bat"

switch ($Action) {
    "start" {
        $existing = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
        if (-not $existing) {
            $action = New-ScheduledTaskAction -Execute $wrapper -WorkingDirectory "D:\brandflow"
            $trigger = New-ScheduledTaskTrigger -AtStartup
            $principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest
            Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Principal $principal -Force
            Write-Host "Task registered with logging wrapper"
        } else {
            # Update existing task's action to use wrapper
            $action = New-ScheduledTaskAction -Execute $wrapper -WorkingDirectory "D:\brandflow"
            Set-ScheduledTask -TaskName $taskName -Action $action
            Write-Host "Task action updated to use logging wrapper"
        }
        Start-ScheduledTask -TaskName $taskName
        Write-Host "Task started"
    }
    "stop" {
        Stop-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
        Write-Host "Task stopped"
    }
    "restart" {
        Stop-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
        Start-ScheduledTask -TaskName $taskName
        Write-Host "Task restarted"
    }
}

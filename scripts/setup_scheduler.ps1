# scripts/setup_scheduler.ps1
# Настройка автоматического запуска импорта (12:10 пн-пт)

$TaskName = "WineAssistant-DailyImport"
$ProjectRoot = "D:\Documents\JetBrainsIDEProjects\PyCharmProjects\wine_assistant"
$PythonExe = "$ProjectRoot\.venv\Scripts\python.exe"
$ScriptPath = "$ProjectRoot\jobs\ingest_dw_price.py"

# Действие: запустить Python скрипт
$Action = New-ScheduledTaskAction `
    -Execute $PythonExe `
    -Argument $ScriptPath `
    -WorkingDirectory $ProjectRoot

# Триггер: пн-пт в 12:10 (Europe/Moscow = UTC+3)
$Trigger = New-ScheduledTaskTrigger `
    -Weekly `
    -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday `
    -At "12:10"

# Настройки
$Settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable

# Создать задачу
Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $Action `
    -Trigger $Trigger `
    -Settings $Settings `
    -User $env:USERNAME `
    -RunLevel Highest `
    -Force

Write-Host "✅ Task Scheduler configured successfully!" -ForegroundColor Green
Write-Host "Task: $TaskName" -ForegroundColor Cyan
Write-Host "Schedule: Mon-Fri at 12:10" -ForegroundColor Cyan
Write-Host ""
Write-Host "To test manually, run:" -ForegroundColor Yellow
Write-Host "Start-ScheduledTask -TaskName '$TaskName'" -ForegroundColor White

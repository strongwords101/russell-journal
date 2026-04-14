# setup-tasks.ps1 - Register all Russell Journal scheduled tasks
# Run once from your normal user account (no admin needed).
# Re-run any time to update settings.

$projectDir     = "C:\Users\shane\Documents\Claude Codespace\russell-journal"
$pythonw        = "C:\Users\shane\AppData\Local\Programs\Python\Python312\pythonw.exe"
$appScript      = Join-Path $projectDir "app.py"
$reminderScript = Join-Path $projectDir "reminder.ps1"
$psArgs         = "-WindowStyle Hidden -NonInteractive -ExecutionPolicy Bypass -File `"$reminderScript`""

# Run tasks as the current logged-in user
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited

# --- 1. Startup server ---
$startupAction   = New-ScheduledTaskAction -Execute $pythonw `
                       -Argument "`"$appScript`"" `
                       -WorkingDirectory $projectDir
$startupTrigger  = New-ScheduledTaskTrigger -AtLogOn -User "$env:USERDOMAIN\$env:USERNAME"
$startupSettings = New-ScheduledTaskSettingsSet `
                       -MultipleInstances IgnoreNew `
                       -RestartCount 3 `
                       -RestartInterval (New-TimeSpan -Minutes 1) `
                       -ExecutionTimeLimit ([TimeSpan]::Zero)

Register-ScheduledTask `
    -TaskName    "RussellJournal-Startup" `
    -Action      $startupAction `
    -Trigger     $startupTrigger `
    -Settings    $startupSettings `
    -Principal   $principal `
    -Description "Start Russell Journal server silently at login" `
    -Force | Out-Null

Write-Host "[OK] Startup task registered (runs at every login, no console window)"

# --- 2. Monday reminder - random window 7:00am to 11:00am ---
$mondayAction  = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $psArgs
$mondayTrigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday -At "07:00"
$mondayTrigger.RandomDelay = "PT4H"

$reminderSettings = New-ScheduledTaskSettingsSet `
                        -ExecutionTimeLimit (New-TimeSpan -Hours 5) `
                        -StartWhenAvailable

Register-ScheduledTask `
    -TaskName    "RussellJournal-Monday" `
    -Action      $mondayAction `
    -Trigger     $mondayTrigger `
    -Settings    $reminderSettings `
    -Principal   $principal `
    -Description "Russell Journal Monday reminder (random 7am-11am)" `
    -Force | Out-Null

Write-Host "[OK] Monday reminder registered (random time, 7am-11am)"

# --- 3. Friday reminder - random window 12:00pm to 3:00pm ---
$fridayTrigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Friday -At "12:00"
$fridayTrigger.RandomDelay = "PT3H"

Register-ScheduledTask `
    -TaskName    "RussellJournal-Friday" `
    -Action      $mondayAction `
    -Trigger     $fridayTrigger `
    -Settings    $reminderSettings `
    -Principal   $principal `
    -Description "Russell Journal Friday reminder (random 12pm-3pm)" `
    -Force | Out-Null

Write-Host "[OK] Friday reminder registered (random time, 12pm-3pm)"
Write-Host ""
Write-Host "All done. To remove all tasks later, run:"
Write-Host "  Get-ScheduledTask -TaskName 'RussellJournal*' | Unregister-ScheduledTask -Confirm:`$false"

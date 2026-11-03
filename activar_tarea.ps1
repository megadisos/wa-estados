# Programa la publicacion diaria en el Programador de tareas de Windows (hora local del PC = Bogota).
# Uso: activar_tarea.bat            -> 05:00 y respaldo 06:30
#      activar_tarea.bat 06:00 07:30
param([string]$Hora1 = "05:00", [string]$Hora2 = "06:30")

$dir = Split-Path -Parent $MyInvocation.MyCommand.Path
$py = Join-Path $dir ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) { Write-Error "Primero ejecuta instalar.bat"; exit 1 }

$accion = New-ScheduledTaskAction -Execute $py -Argument "publicar.py" -WorkingDirectory $dir
$disparadores = @((New-ScheduledTaskTrigger -Daily -At $Hora1), (New-ScheduledTaskTrigger -Daily -At $Hora2))
$ajustes = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable -WakeToRun `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -RunOnlyIfNetworkAvailable `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Hours 1)
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName "EstadosWhatsApp" -Action $accion -Trigger $disparadores `
    -Settings $ajustes -Principal $principal -Force | Out-Null
Write-Host "Tarea 'EstadosWhatsApp' creada: $Hora1 y respaldo $Hora2 (todos los dias)."
Write-Host "Probarla ya:  schtasks /Run /TN EstadosWhatsApp"

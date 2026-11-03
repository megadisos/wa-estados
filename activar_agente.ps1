# Deja corriendo el agente de la app (agente.py) cada vez que inicias sesion en Windows.
# Uso: activar_agente.bat        (pide permiso de administrador una vez para abrir el puerto en el firewall)
param([int]$Puerto = 8770)

$dir = Split-Path -Parent $MyInvocation.MyCommand.Path
$pyw = Join-Path $dir ".venv\Scripts\pythonw.exe"
$py = Join-Path $dir ".venv\Scripts\python.exe"
if (-not (Test-Path $pyw)) { Write-Error "Primero ejecuta instalar.bat"; exit 1 }

# 1) Tarea al iniciar sesion (sin ventana), que se reinicia sola si se cae
$accion = New-ScheduledTaskAction -Execute $pyw -Argument "agente.py --puerto $Puerto" -WorkingDirectory $dir
$disparador = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$ajustes = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName "AgenteEstadosWhatsApp" -Action $accion -Trigger $disparador `
    -Settings $ajustes -Principal $principal -Force | Out-Null
Start-ScheduledTask -TaskName "AgenteEstadosWhatsApp"
Write-Host "Tarea 'AgenteEstadosWhatsApp' creada y en marcha (arranca sola al iniciar sesion)."

# 2) Firewall: solo se permite la red de Tailscale (100.64.0.0/10), nunca todo internet
$regla = "Agente Estados WhatsApp (Tailscale)"
$cmd = "Remove-NetFirewallRule -DisplayName '$regla' -ErrorAction SilentlyContinue; " +
       "New-NetFirewallRule -DisplayName '$regla' -Direction Inbound -Protocol TCP -LocalPort $Puerto " +
       "-RemoteAddress 100.64.0.0/10 -Action Allow | Out-Null"
try {
    Start-Process powershell -Verb RunAs -Wait -ArgumentList "-NoProfile -Command $cmd"
    Write-Host "Firewall: puerto $Puerto abierto solo para Tailscale."
} catch {
    Write-Warning "No se pudo abrir el puerto en el firewall (se necesita aceptar el permiso de administrador)."
}

# 3) Datos para la app
$clave = & $py (Join-Path $dir "agente.py") --mostrar-clave
$ip = $null
$ts = Get-Command tailscale -ErrorAction SilentlyContinue
if (-not $ts) { $ts = Get-Item "C:\Program Files\Tailscale\tailscale.exe" -ErrorAction SilentlyContinue }
if ($ts) { $ip = (& $ts.Source ip -4 2>$null | Select-Object -First 1) }
Write-Host ""
Write-Host "==== Datos para la app del celular ===="
if ($ip) { Write-Host "Direccion: http://${ip}:$Puerto" } else { Write-Host "Direccion: http://<IP de Tailscale del PC>:$Puerto  (instala Tailscale y mira su IP 100.x.x.x)" }
Write-Host "Clave:     $clave"
Write-Host "======================================="

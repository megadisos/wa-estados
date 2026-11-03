# Estados automáticos de WhatsApp – Customania (PC de casa con Windows)

Publica cada día a las 5:00 a.m., en tus dos cuentas (customania y personal), 7 estados:
la PROMO DE LA SEMANA de customania.com.co/promos + 3 servicios de customania.com.co/servicios
+ 3 productos de la tienda (sin medallas ni trofeos).
Cada día son distintos y no se repiten hasta recorrer todo el catálogo; luego empieza otra vuelta mezclada.

## Instalación en Windows (una vez)
1. Instala Python 3.10 o superior desde python.org (marca "Add python to PATH"). Usa Windows normal, no WSL.
2. Descomprime esta carpeta donde quieras (por ejemplo C:\wa-estados) y haz doble clic en `instalar.bat`.
3. Abre una consola (cmd) dentro de la carpeta y ejecuta, una por cuenta:
       login.bat customania
       login.bat personal
   Se abre una ventana de Chromium con el QR: escanéalo desde WhatsApp > Dispositivos vinculados.
   Se hace UNA sola vez por cuenta (la sesión queda guardada en datos\perfiles).

## Pruebas antes de activar (en este orden, desde cmd en la carpeta)
    .venv\Scripts\python publicar.py --dry-run
Muestra el plan y los textos y crea las imágenes en datos\tarjetas_preview (no abre WhatsApp ni gasta la rotación).

    .venv\Scripts\python publicar.py --sin-enviar --depurar --forzar --cuenta personal
Abre WhatsApp Web, llega hasta el botón Enviar y NO envía. Si falla, mira datos\capturas\<cuenta>\
(captura + archivo _ui.json) y se ajusta la lista SEL de whatsapp.py.

    .venv\Scripts\python publicar.py --forzar --sin-espera --cuenta personal
Publica de verdad en tu cuenta personal. Revisa el celular.

## Activar las 5:00 a.m.
    activar_tarea.bat
Crea la tarea "EstadosWhatsApp" en el Programador de tareas: 05:00 todos los días y un respaldo a las 06:30
(si a las 05:00 ya se publicó todo, el respaldo no hace nada; si algo falló, completa lo que falte sin duplicar).
Otras horas: `activar_tarea.bat 06:00 07:30`. Probarla ya: `schtasks /Run /TN EstadosWhatsApp`.
Quitarla: `schtasks /Delete /TN EstadosWhatsApp /F`.

Para que funcione a las 5:00 a.m.:
- El PC puede estar dormido (la tarea lo despierta), pero NO apagado del todo. Si prefieres apagarlo, programa el
  encendido en la BIOS/UEFI (RTC alarm / "Power on by alarm") unos minutos antes.
- Tu sesión de Windows debe estar iniciada (puede estar bloqueada con Win+L). Es necesario porque el navegador se abre en pantalla.
- En Opciones de energía deja habilitados los "temporizadores de reactivación" (Allow wake timers).
- Si el PC estaba apagado a las 5:00, la tarea corre apenas se encienda (siempre que sea entre 4:00 y 20:30, ver config.toml).
Verás una ventana de consola y otra de Chromium unos minutos: es normal.

## IMPORTANTE: apaga lo que ya tenías
Desactiva el script anterior de Selenium (o los dos publicarían a la vez y saldrían estados duplicados).
En cada celular, entra a WhatsApp > Dispositivos vinculados y cierra la sesión del Selenium viejo: WhatsApp permite
pocos dispositivos vinculados y así no acumulas sesiones. Como este programa usa su propio perfil de navegador, hay que
escanear el QR una vez más; es esperado.

## Promo de la semana
Cada día el programa abre customania.com.co/promos (sin ventana), mira cuál es "la de esta semana", entra a su página
y toma la imagen principal. Esa imagen sale como el primer estado del día, todos los días de lunes a domingo; cuando
la página cambia de promo, el estado cambia solo. El texto del estado se ajusta en config.toml ([textos] promo).
- Verifícalo con  publicar.py --dry-run : en el log sale "Promo de la semana detectada: ..." y la imagen queda en
  datos\tarjetas_preview\<fecha>\1_promo_....jpg
- Si detecta la equivocada o falla, fíjala a mano en config.toml: [promo_semana] forzar = "mugs-personalizados"
  (el final de la URL de la promo). Acuérdate de vaciarla ("") la semana siguiente.
- Si no puede leer la promo, avisa (log/Telegram) y publica igual los otros 6 estados.
- Para desactivarla: [promo_semana] activa = false

## Ajustes (config.toml)
- [promo_semana]: activar/desactivar, posición (primero/último) o fijarla a mano
- servicios_por_dia / productos_por_dia, excluir_productos, excluir_servicios
- textos de los estados (y textos distintos por cuenta con [cuentas.textos])
- pausas entre estados/cuentas y espera aleatoria inicial (jitter_inicio_min = 0 para hora exacta)
- ventana horaria de seguridad (no publica antes de las 4:00 ni después de las 20:30)
- alertas por Telegram si algo falla

## Reducir el riesgo de bloqueo
WhatsApp no ofrece API oficial para Estados; esto usa WhatsApp Web, lo que va contra sus términos.
El riesgo con 7 estados al día es bajo pero no es cero. Lo que más ayuda:
- Correr desde tu PC de casa (IP residencial y siempre la misma) es mejor que un servidor.
- Escanear el QR una sola vez y no re-vincular seguido.
- Mantener el celular con internet: WhatsApp cierra dispositivos vinculados tras ~14 días sin conexión del teléfono.
- No usar esta sesión para mensajes masivos; solo publica estados.
- No subir las cantidades ni quitar las pausas.

## Si algo falla
- "pide escanear el QR": se cerró la sesión. Ejecuta de nuevo  login.bat <cuenta>.
- "Paso 'x' falló": WhatsApp cambió la interfaz. Manda la captura y el _ui.json y se ajusta SEL.
- Logs: datos\logs\estados.log
- Un estado "incierto" (se dio clic en Enviar pero no se pudo confirmar) NO se reintenta solo, para no duplicar.

## Linux/VPS (opcional)
Siguen incluidos instalar.sh, login.sh y activar_timer.sh (por defecto también 05:00 y respaldo 06:30).

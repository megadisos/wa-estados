# App Android "Estados WA"

Control remoto de los estados de WhatsApp desde el celular. Habla con `agente.py`, que corre en el PC.
Las instrucciones de instalación están en el [LEEME.md](../LEEME.md) principal, sección "App del celular".

Desarrollo:

    flutter pub get
    flutter analyze && flutter test
    flutter build apk --release

GitHub Actions (`.github/workflows/apk.yml`) compila el APK en cada cambio dentro de `app/` y lo publica en
Releases: `app-ultima` desde `main` y `app-prueba` desde otras ramas.

## Firma propia (opcional, para actualizar sin desinstalar)

Sin firma propia, cada APK de GitHub sale con una llave distinta y Android obliga a desinstalar antes de actualizar.
Para evitarlo, una sola vez en un PC con Java:

    keytool -genkeypair -v -keystore firma.jks -alias estados -keyalg RSA -keysize 2048 -validity 10000

Luego en GitHub > Settings > Secrets and variables > Actions crea:
- `ANDROID_KEYSTORE_BASE64`: el contenido de `firma.jks` en base64 (`certutil -encode firma.jks firma.txt` en Windows,
  copiando solo lo que hay entre las líneas BEGIN/END; o `base64 -w0 firma.jks` en Linux).
- `ANDROID_KEYSTORE_PASSWORD`: la contraseña que pusiste.

Guarda `firma.jks` en un lugar seguro y nunca lo subas al repositorio.

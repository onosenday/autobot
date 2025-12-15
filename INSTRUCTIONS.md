# 🏎️ Real Racing 3 Bot - Instrucciones de Uso

Este bot automatiza el proceso de ver anuncios para farmear oro en Real Racing 3 utilizando ADB.

## 📋 Requisitos Previos

1.  **Android Debug Bridge (ADB)**: Debe estar instalado y configurado en tu sistema.
    *   Ubuntu/Debian: `sudo apt install adb`
2.  **Dispositivo Android**:
    *   Conectado por USB.
    *   Depuración USB activada.
    *   (Opcional pero recomendado) Pantalla configurada para no bloquearse o usar el modo "Stay Awake" en opciones de desarrollador.
    *   **Nota para Xiaomi**: Activar "Depuración USB (Ajustes de seguridad)" para permitir clicks simulados.
3.  **Python 3.10+**.

## 🚀 Instalación

1.  Crear y activar un entorno virtual (recomendado):
    ```bash
    python3 -m venv venv
    source venv/bin/activate
    ```

2.  Instalar dependencias:
    ```bash
    pip install -r requirements.txt
    ```

## 🎮 Ejecución

El método más sencillo es usar el script de lanzamiento:

```bash
./run.sh
```

Alternativamente, puedes ejecutar la interfaz gráfica manualmente:

```bash
source venv/bin/activate
python gui.py
```

## ⚙️ Funcionamiento

1.  Al iniciar, se abrirá una ventana
2.  Conecta tu móvil y asegúrate de que ADB lo reconoce (`adb devices`).
3.  Pulsa **Iniciar** en la GUI.
4.  El bot:
    *   Abrirá Real Racing 3 si no está en primer plano.
    *   Buscará ofertas de anuncios de oro.
    *   Verá los anuncios y los cerrará.
    *   Recolectará la recompensa.
    *   Si se acaban los anuncios, puede intentar cambiar la zona horaria (Kiritimati/Madrid) si está configurado.

## ⚠️ Notas Importantes

*   **Bloqueo de Pantallas**: El bot intenta mantener el dispositivo activo, pero es mejor configurar el móvil para que la pantalla no se apague nunca mientras carga.
*   **Interrupción**: Para detener el bot de forma segura, pulsa "Parar" en la GUI o presiona `Ctrl+C` en la terminal.
*   **Logs**: Se guarda un registro de ganancias en `gold_log.db`.

Para información técnica más detallada, consulta [AGENTS.md](AGENTS.md).

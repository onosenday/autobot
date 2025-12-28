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

### ⚡ Aceleración por GPU (Opcional - Recomendado)

Si dispones de una tarjeta gráfica NVIDIA, puedes acelerar el entrenamiento del modelo ML significativamente.

1.  **Instalar Drivers de NVIDIA**:
    En Ubuntu/Debian:
    ```bash
    sudo apt update
    sudo apt install nvidia-driver-535  # O la versión más reciente compatible
    sudo reboot
    ```
    Verifica la instalación con `nvidia-smi`.

2.  **Instalar Pytorch con soporte CUDA**:
    Por defecto, `pip install` puede instalar la versión de solo CPU. Para activar la GPU, ejecuta:
    ```bash
    # Asegúrate de tener el entorno virtual activado
    source venv/bin/activate
    
    # Desinstalar versión CPU si existe
    pip uninstall -y torch torchvision torchaudio

    # Instalar versión con CUDA 12.1
    pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
    ```

3.  **Verificar Soporte CUDA en Python**:
    Con el entorno virtual activado:
    ```bash
    python3 -c "import torch; print(f'CUDA disponible: {torch.cuda.is_available()}')"
    ```
    Si imprime `True`, el bot usará la GPU automáticamente.

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

## ⚙️ Funcionamiento y GUI

1.  **Ventana Principal**:
    *   **Iniciar/Parar**: Control del ciclo del bot.
    *   **Live View**: Muestra lo que el bot está viendo en tiempo real.
    *   **Métricas**: Oro ganado hoy, total histórico y ritmo (Oro/Hora).
2.  **Gráfico de Ganancias**:
    *   Haz click en el icono de gráfico para ver el histórico de los últimos 7 días.
    *   Se actualiza automáticamente cada minuto mientras la ventana esté abierta.
3.  **Ciclo Automático**:
    *   El bot busca la moneda de oro, confirma el anuncio, lo ve y cierra la ventana de recompensa.
    *   **Kiritimati Trick**: Si "No hay más anuncios" aparece, el bot cambiará automáticamente la zona horaria del dispositivo entre Madrid y Kiribati para resetear el límite de anuncios.

## 🛠 Solución de Problemas (Troubleshooting)

### El bot se queda atascado en el cambio de zona horaria
*   **Posible causa**: La lupa de búsqueda en Ajustes de Android ha cambiado de posición.
*   **Solución**: El bot intenta usar OCR para encontrarla, pero si falla, puedes verificar el archivo `main.py` -> `handle_timezone_sequence` y ajustar las coordenadas de fallback o los términos de búsqueda ("Kiribati", "Espa").

### El bot no cierra los anuncios
*   **Posible causa**: El botón "X" es muy pequeño o tiene un diseño nuevo.
*   **Solución**: El bot usa detección dinámica de "X". Asegúrate de que el brillo de la pantalla en la captura se vea bien (no negro).

### Errores de ADB
*   Asegúrate de que solo hay un dispositivo conectado o especifica el serial si es necesario.
*   Prueba a reiniciar el servidor: `adb kill-server && adb start-server`.

## ⚠️ Notas Importantes

*   **Horario de Funcionamiento**: Por defecto, el bot solo opera de **12:00 a 00:00** (Configurable en `config.py`). Fuera de ese horario entrará en pausa automática.
*   **Logs**: Todos los registros se guardan en `gold_log.db` (SQLite). No lo borres si quieres conservar las estadísticas.



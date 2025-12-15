# Análisis de Migración a `scrcpy-client`

Este documento detalla la estimación y el impacto de cambiar la implementación actual basada en `adbutils` (pulling de screenshots) a `scrcpy-client` (streaming de video H.264 + socket de control).

## 1. Estimación del Coste (Esfuerzo de Desarrollo)
**Nivel: Medio** (Aprox. 3-5 horas de trabajo)

*   **Refactorización de `ADBWrapper`**: Es necesario reescribir la clase casi por completo.
    *   Cambiar el modelo de "pedir captura" (síncrono) a "recibir stream" (asíncrono/threading).
    *   Implementar un hilo de escucha para mantener actualizado el `last_frame` en memoria.
    *   Implementar el manejo de eventos de toque (Touch) usando el protocolo de scrcpy en lugar de comandos shell.
*   **Gestión de Dependencias**: Asegurar que el servidor `.jar` de scrcpy compatible se suba y ejecute correctamente en el dispositivo.
*   **Pruebas**: Verificar estabilidad de conexión de larga duración.

## 2. Impacto en la Ejecución

### Rendimiento (Visión)
*   **Actual (`adbutils`)**:
    *   Latencia alta (200ms - 800ms por captura).
    *   FPS bajos (1-3 FPS efectivos).
    *   Carga en CPU (PC) baja/media (decodificación PNG).
*   **Nuevo (`scrcpy-client`)**:
    *   **Latencia ultra-baja** (30ms - 100ms).
    *   **FPS altos** (configurable, hasta 60 FPS).
    *   **Carga en CPU (PC) mayor**: Decodificar un stream H.264 en tiempo real consume más recursos que capturas esporádicas.

### Rendimiento (Input)
*   **Actual**: `input swipe` vía shell es lento (~300ms de overhead por comando).
*   **Nuevo**: Input vía socket persistente es instantáneo (<5ms). *Nota: Esto soluciona los problemas de swipes rápidos y gestos complejos.*

## 3. Ventajas e Inconvenientes

| Característica | `adbutils` (Actual) | `scrcpy-client` (Propuesto) |
| :--- | :--- | :--- |
| **Velocidad de Reacción** | Lenta. Puede perder eventos rápidos. | Inmediata. Ideal para sincronización precisa. |
| **Estabilidad** | Alta. Si falla una request, la siguiente funciona. | Media. Si el stream se rompe, hay que reiniciar el cliente completo. |
| **Code Simplicity** | Simple (request-response). | Complejo (Threads, Callbacks, Buffers). |
| **Uso de Recursos** | Bajo/Bajo demanda. | Constante (decodificando video incluso si no miras). |
| **Compatibilidad** | Universal (funciona en casi cualquier Android). | Requiere Android 5.0+ y soporte H.264 decente. |

## 4. Riesgos y Posibilidad de Bugs

### Riesgo de Regresión: ALTO en el corto plazo
Al cambiar el núcleo de interacción (visión + input), es muy probable que surjan bugs iniciales:

1.  **Frames "Viejos"**: Si el hilo de decodificación se retrasa, el bot podría tomar decisiones basadas en lo que pasó hace 2 segundos (lag de buffer).
2.  **Desconexiones Silenciosas**: Si el servidor scrcpy muere en el móvil, el bot podría quedarse viendo la última imagen congelada "para siempre" si no implementamos detección de heartbeat.
3.  **Conflictos con Xiaomi**: `adbutils` usa hacks de `swipe` para evitar la seguridad de Xiaomi. `scrcpy` usa inyección de eventos directa; en algunos dispositivos Xiaomi esto **requiere habilitar explícitamente "Depuración USB (ajustes de seguridad)"**, lo cual a veces se resetea o requiere SIM.

## Conclusión

El cambio es **recomendable** si buscas maximizar la velocidad y hacer el bot más "humano" y reactivo.
Si la prioridad es la **estabilidad absoluta y simplicidad**, `adbutils` es suficiente para un juego por turnos o lento como RR3 (en menús). Para las carreras o anuncios rápidos, `scrcpy` es superior.

**Recomendación**: Mantener `adbutils` como fallback o implementar `scrcpy` en una rama separada para pruebas intensivas.

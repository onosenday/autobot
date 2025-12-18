# RR3 Bot - AGENTS.md

## 🤖 Contexto del Proyecto
Bot de automatización para **Real Racing 3** en Android para **farmear oro** viendo anuncios.

### 🚧 Desafío Crítico (Xiaomi/Android 11+)
**Solución**: Pure ADB con 'Robust Taps' (`input swipe x y x y 100`).

---

## 📂 Arquitectura del Código

| Archivo | Función |
|:--------|:--------|
| `gui.py` | Control, Live View, Métricas, Gráfico 7 días |
| `main.py` | Máquina de Estados Reactiva |
| `vision.py` | Template Matching con `find_template_adaptive` |
| `ocr.py` | Tesseract con `find_text_adaptive` |
| `logger.py` | SQLite: oro + memoria OCR/Template |

---

## 🎮 Máquina de Estados Principal

| Estado | Descripción | Transiciones |
|:-------|:------------|:-------------|
| `UNKNOWN` | Inicial/Recuperación | → `GAME_LOBBY` |
| `GAME_LOBBY` | Busca moneda/intermedia/no más oro | → `AD_INTERMEDIATE`, `REWARD_SCREEN`, `TZ_INIT` |
| `AD_INTERMEDIATE` | Confirmación de anuncio | → `AD_WATCHING` |
| `AD_WATCHING` | Monitoreo (70s timeout, X, FF, Web, Encuesta) | → `REWARD_SCREEN` |
| `REWARD_SCREEN` | OCR oro, cierra ventana | → `GAME_LOBBY` |
| `TZ_*` | Sub-máquina Timezone | → `GAME_LOBBY` |

---

## 🌍 Sub-Máquina: Timezone Switch

| Estado | Acción | Memoria Guardada |
|:-------|:-------|:-----------------|
| `TZ_OPEN_SETTINGS` | `am start DATE_SETTINGS` | - |
| `TZ_SEARCH_REGION` | OCR "Region"/"Seleccionar" | `ocr_tz_region`, `ocr_tz_seleccionar` |
| `TZ_INPUT_SEARCH` | Lupa + escribir término | `tmpl_search_icon` |
| `TZ_SELECT_COUNTRY` | OCR país + click | `ocr_tz_pais_kiribati`, `ocr_tz_pais_espa` |
| `TZ_SELECT_CITY` | OCR ciudad (sin fallback) | `tz_city_kiritimati`, `tz_city_madrid` |
| `TZ_RETURN_GAME` | `am start` juego | - |

---

## 🧠 Sistema de Memoria Adaptativa

Guarda última posición exitosa para acelerar futuras búsquedas.

### Elementos con Memoria:

| # | Tipo | Elemento | Memory Key |
|:--|:-----|:---------|:-----------|
| 1 | Template | Moneda de Oro | `tmpl_coin_icon` |
| 2 | Template | Pantalla Intermedia | `tmpl_intermediate` |
| 3 | Template | Botón Confirmar | `tmpl_ad_confirm` |
| 4 | Template | No Más Oro | `tmpl_no_more_gold` |
| 5 | Template | Cerrar Recompensa | `tmpl_reward_close_*` |
| 6 | Template | Lupa Búsqueda | `tmpl_search_icon` |
| 7 | OCR | Region | `ocr_tz_region` |
| 8 | OCR | Seleccionar | `ocr_tz_seleccionar` |
| 9 | OCR | País Kiribati | `ocr_tz_pais_kiribati` |
| 10 | OCR | País España | `ocr_tz_pais_espa` |
| 11 | OCR | Ciudad Madrid | `tz_city_madrid` |
| 12 | OCR | Ciudad Kiritimati | `tz_city_kiritimati` |

---

## 🚨 Reglas para Agentes AI

### Ficheros Protegidos por `.gitignore`
1.  Eliminar temporalmente la línea en `.gitignore`
2.  Editar el fichero
3.  Restaurar `.gitignore` inmediatamente

### Pruebas y Debugging
*   Usar carpeta separada: `_debug_tmp/`
*   Borrar al finalizar
*   **Prohibido** mezclar basura con código fuente

---
**Ejecución:** `./run.sh`

---

## 🧪 Funciones Experimentales

### ML Training Data Collection (PENDIENTE VALIDACIÓN)
> [!WARNING]
> Esta función es **EXPERIMENTAL** y requiere validación antes de considerarse estable.

- **Estado**: En pruebas
- **Archivos**: `ml_logger.py`, modificaciones en `main.py`
- **Datos**: `ml_data.db` + `training_data/` (JPEG 85% grayscale)
- **Toggle**: `self.ml_enabled = True/False` en `RealRacingBot.__init__`

**Pendiente de validar**:
- [ ] Screenshots se guardan correctamente
- [ ] Transiciones se registran en BD
- [ ] Recompensas se calculan correctamente
- [ ] Espacio en disco es manejable

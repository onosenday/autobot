#!/bin/bash
# Real Racing 3 Bot - Launcher Script

cd "$(dirname "$0")"

echo "🏁 Iniciando Real Racing 3 Bot..."

# Activar entorno virtual
if [ -d "venv" ]; then
    source venv/bin/activate
    echo "✓ Entorno virtual activado"
else
    echo "❌ Error: No se encuentra el entorno virtual (venv)"
    exit 1
fi

# Ejecutar GUI
python3 gui.py

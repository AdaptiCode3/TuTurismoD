#!/usr/bin/env bash
# exit on error
set -o errexit

echo "📦 Instalando dependencias del Backend de Tu-Turismo..."
pip install -r requirements.txt

echo "🎨 Recopilando archivos estáticos..."
python manage.py collectstatic --no-input

echo "✅ Build del Backend completado con éxito."

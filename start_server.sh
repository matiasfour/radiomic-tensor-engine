#!/bin/bash

echo "🚀 Iniciando DKI Radiomic Workstation..."

# 1. Levantar la base de datos Postgres (por si el Studio se durmió)
sudo service postgresql start

# 2. Limpieza de Caché y Archivos Temporales
echo "🧹 Limpiando estáticos y archivos temporales..."
rm -rf backend/staticfiles/*
# Descomenta la siguiente línea para borrar resultados de procesamiento previos:
# rm -rf /teamspace/studios/this_studio/media/results/*

# 3. Instalación de dependencias críticas
echo "📦 Verificando dependencias..."
pip install -r backend/requirements.txt --quiet

# 4. Preparar Django
export LIGHTNING_CLOUD=true
cd backend

echo "📂 Recopilando estáticos (Frontend)..."
python manage.py collectstatic --noinput --clear

echo "🔄 Aplicando migraciones de base de datos..."
python manage.py migrate --noinput

# 5. Arrancar Gunicorn (Producción)
echo "✅ Servidor listo en puerto 8000"
gunicorn dki_backend.wsgi:application \
    --bind 0.0.0.0:8000 \
    --workers 3 \
    --timeout 600 \
    --access-logfile - \
    --error-logfile -

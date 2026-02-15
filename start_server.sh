#!/bin/bash

# Lightning AI Startup Script
# Usage: ./start_server.sh

echo "⚡ Starting DKI Radiomic Workstation..."

# 1. Asegurar que Postgres esté corriendo
sudo service postgresql start

# 2. Instalar dependencias (por si acaso)
echo "📦 Installing Python dependencies..."
pip install -r backend/requirements.txt

# 3. Preparar Django
export LIGHTNING_CLOUD=true
export DB_ENGINE=postgresql
cd backend

echo "🔄 Running migrations..."
python3 manage.py collectstatic --noinput
python3 manage.py migrate

# 4. Lanzar Servidor de Producción (Gunicorn)
# Usamos Gunicorn porque es más robusto que runserver
# Bind 0.0.0.0:8080 para que sea público
echo "🚀 Servidor listo en puerto 8080 con Postgres"
gunicorn dki_backend.wsgi:application --bind 0.0.0.0:8080 --workers 3 --timeout 600

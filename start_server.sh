#!/bin/bash

# Lightning AI Startup Script
# Usage: ./start_server.sh

echo "⚡ Starting DKI Radiomic Workstation..."

# 1. Install Dependencies
echo "📦 Installing Python dependencies..."
pip install -r backend/requirements.txt

# 2. Database Migrations
echo "🗄️ Applying database migrations..."
cd backend
python3 manage.py migrate

# 3. Collect Static Files
echo "🎨 Collecting static files..."
python3 manage.py collectstatic --noinput

# 4. Start Gunicorn
echo "🚀 Launching Application on port 8000..."
# 4 workers, binding to 0.0.0.0 to be accessible externally
gunicorn dki_backend.wsgi:application --bind 0.0.0.0:8000 --workers 4

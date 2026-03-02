#!/bin/bash

echo "🚀 Iniciando DKI Radiomic Workstation..."

# ==============================
# 1. CONFIGURACIÓN POSTGRES
# ==============================

if [ -d "/teamspace/studios/this_studio" ]; then
    echo "⚡ Entorno Lightning AI detectado. Configurando PostgreSQL persistente..."

    export LIGHTNING_CLOUD=true

    sudo service postgresql stop || true

    PG_DATA_DIR="/teamspace/studios/this_studio/postgres_data"

    if [ ! -d "$PG_DATA_DIR" ]; then
        echo "📂 Creando directorio persistente en $PG_DATA_DIR..."
        sudo mkdir -p "$PG_DATA_DIR"
        sudo chown postgres:postgres "$PG_DATA_DIR"

        if [ -d "/var/lib/postgresql/14/main" ]; then
            sudo rsync -a /var/lib/postgresql/14/main/ "$PG_DATA_DIR/"
        fi
    fi

    if [ -f "/etc/postgresql/14/main/postgresql.conf" ]; then
        sudo sed -i "s|data_directory = '.*'|data_directory = '$PG_DATA_DIR'|g" \
        /etc/postgresql/14/main/postgresql.conf
    fi

    sudo service postgresql start

    echo "🛡️ Verificando usuario y base de datos..."
    sudo -u postgres psql -tAc "SELECT 1 FROM pg_roles WHERE rolname='matias'" | grep -q 1 || \
    sudo -u postgres psql -c "CREATE USER matias WITH SUPERUSER PASSWORD 'crescendo2026';"

    sudo -u postgres psql -tAc "SELECT 1 FROM pg_database WHERE datname='dki_db'" | grep -q 1 || \
    sudo -u postgres psql -c "CREATE DATABASE dki_db OWNER matias;"

    # ==============================
    # 2. AJUSTAR PYTHON PARA VMTK
    # ==============================

    echo "🐍 Verificando versión de Python..."

    PY_CURRENT=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")

    if [ "$PY_CURRENT" != "3.10" ]; then
        echo "⚠️ Python actual es $PY_CURRENT — cambiando a 3.10 para compatibilidad con VMTK..."
        conda install python=3.10 -y
    else
        echo "✅ Python ya es 3.10"
    fi

    # ==============================
    # 3. INSTALAR VMTK
    # ==============================

    export VMTK_ENV_DIR="SYSTEM"

    if python3 -c "import vmtk; import vtk" 2>/dev/null; then
        echo "✅ VMTK ya disponible."
    else
        echo "🔬 Instalando VMTK (~5-10 min la primera vez)..."
        conda install -c vmtk -c conda-forge vmtk -y

        if python3 -c "import vmtk; import vtk" 2>/dev/null; then
            echo "✅ VMTK instalado correctamente."
        else
            echo "⚠️ VMTK no disponible — se usará segmentación HU de respaldo."
        fi
    fi

else
    echo "💻 Entorno local detectado. Iniciando PostgreSQL normalmente..."
    sudo service postgresql start || echo "ℹ️ Ignorado si no usas systemd"
fi


# ==============================
# 4. LIMPIEZA
# ==============================

echo "🧹 Limpiando archivos temporales..."
rm -rf backend/staticfiles/*


# ==============================
# 5. INSTALAR DEPENDENCIAS
# ==============================

echo "📦 Instalando dependencias Python..."
pip install --upgrade pip
pip install -r backend/requirements.txt


# ==============================
# 6. PREPARAR DJANGO
# ==============================

export LIGHTNING_CLOUD=true
cd backend

echo "📂 Collectstatic..."
python manage.py collectstatic --noinput --clear

echo "🔄 Migraciones..."
python manage.py migrate --noinput


# ==============================
# 7. ARRANCAR GUNICORN
# ==============================

echo "✅ Servidor listo en puerto 8000"

gunicorn dki_backend.wsgi:application \
    --bind 0.0.0.0:8000 \
    --workers 3 \
    --timeout 600 \
    --access-logfile - \
    --error-logfile -
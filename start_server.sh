#!/bin/bash

echo "🚀 Iniciando DKI Radiomic Workstation..."

# 1. Levantar la base de datos Postgres (por si el Studio se durmió)
# Detectar si estamos en Lightning AI
if [ -d "/teamspace/studios/this_studio" ]; then
    echo "⚡ Entorno Lightning AI detectado. Configurando PostgreSQL persistente..."
    
    export LIGHTNING_CLOUD=true
    
    # Detener postgres temporalmente si inició con el directorio efímero
    sudo service postgresql stop || true
    
    PG_DATA_DIR="/teamspace/studios/this_studio/postgres_data"
    
    # 1.a Mover los datos persistentes si es la primera vez
    if [ ! -d "$PG_DATA_DIR" ]; then
        echo "📂 Creando directorio de datos persistente en $PG_DATA_DIR..."
        sudo mkdir -p "$PG_DATA_DIR"
        sudo chown postgres:postgres "$PG_DATA_DIR"
        # Sincronizar los datos iniciales de postgres al volumen persistente (asumiendo versión 14)
        if [ -d "/var/lib/postgresql/14/main" ]; then
            sudo rsync -a /var/lib/postgresql/14/main/ "$PG_DATA_DIR/"
        fi
    fi
    
    # 1.b Actualizar el directorio de datos en la configuración de Postgres
    if [ -f "/etc/postgresql/14/main/postgresql.conf" ]; then
        # Reemplazar la ruta de data_directory en la línea adecuada
        sudo sed -i "s|data_directory = '.*'|data_directory = '$PG_DATA_DIR'|g" /etc/postgresql/14/main/postgresql.conf
    fi
    
    # 1.c Iniciar postgres con la configuración apuntando al volumen persistente
    sudo service postgresql start
    
    # 1.d Asegurar que el usuario y la base de datos base existan
    echo "🛡️ Verificando base de datos y usuario..."
    sudo -u postgres psql -tAc "SELECT 1 FROM pg_roles WHERE rolname='matias'" | grep -q 1 || sudo -u postgres psql -c "CREATE USER matias WITH SUPERUSER PASSWORD 'crescendo2026';"
    sudo -u postgres psql -tAc "SELECT 1 FROM pg_database WHERE datname='dki_db'" | grep -q 1 || sudo -u postgres psql -c "CREATE DATABASE dki_db OWNER matias;"

    # 1.e Entorno VMTK en almacenamiento persistente (solo se crea la primera vez)
    # Los envs en /home/zeus/miniconda3/envs/ se pierden al reiniciar el Studio.
    # Lo instalamos en /teamspace/ con --prefix para que persista.
    VMTK_ENV_DIR="/teamspace/studios/this_studio/conda_envs/vmtk_env"
    export VMTK_ENV_DIR
    if [ ! -f "$VMTK_ENV_DIR/bin/python" ]; then
        echo "🔬 Creando entorno VMTK en $VMTK_ENV_DIR (primera vez, ~5-10 min)..."
        conda create --prefix "$VMTK_ENV_DIR" python=3.9 -y
        conda install --prefix "$VMTK_ENV_DIR" -c vmtk vmtk -y
        echo "✅ Entorno VMTK creado correctamente."
    else
        echo "✅ Entorno VMTK encontrado en $VMTK_ENV_DIR (omitiendo instalación)."
    fi

else
    echo "💻 Entorno local detectado. Iniciando PostgreSQL normalmente..."
    sudo service postgresql start || echo "ℹ️ (Ignorado si no estás usando Linux/systemd)"
fi

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

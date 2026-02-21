#!/bin/bash

# Este script debe ejecutarse en el ambiente de Lightning AI para inicializar 
# la base de datos Postgres y el usuario en caso de que no existan o se hayan borrado.
#
# Para ejecutarlo, ábrelo en Lightning AI y corre:
# chmod +x init_db.sh
# ./init_db.sh

echo "🛠️ Inicializando base de datos Postgres para DKI..."

# 1. Aseguramos que el servicio de postgres esté corriendo
sudo service postgresql start

# 2. Creamos el usuario 'matias' con el password 'crescendo2026'
# Usamos sudo -u postgres para ejecutar el comando como el súper usuario de DB
echo "👤 Creando usuario de base de datos 'matias'..."
sudo -u postgres psql -c "CREATE USER matias WITH PASSWORD 'crescendo2026';" || echo "El usuario ya existe, ignorando..."

# Le damos permisos para crear bases de datos (opcional pero recomendado en Django)
sudo -u postgres psql -c "ALTER USER matias CREATEDB;"

# 3. Creamos la base de datos 'dki_db' asignándole como dueño a 'matias'
echo "📦 Creando base de datos 'dki_db'..."
sudo -u postgres psql -c "CREATE DATABASE dki_db OWNER matias;" || echo "La base de datos ya existe, ignorando..."

echo "✅ Listo. Ahora puedes correr ./start_server.sh"

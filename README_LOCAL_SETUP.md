# 🚀 Guía de Instalación para "DKI / MART" (Windows y Mac)

Esta guía te ayudará a instalar y ejecutar el proyecto desde cero en una computadora nueva.

Elige tu sistema operativo y sigue los pasos:

---

# 🪟 Opción A: WINDOWS

## Paso 0: Instalar Herramientas Básicas
Necesitamos instalar Python, Node.js y Git. En Windows, lo más fácil es usar los instaladores oficiales o el comando `winget` en PowerShell.

1.  **Abrir PowerShell como Administrador**: Haz clic derecho en el botón de Inicio y elige "Windows PowerShell (Administrador)" o "Terminal (Administrador)".
2.  **Ejecuta estos comandos uno por uno** (o descarga los instaladores de sus webs oficiales):
    ```powershell
    winget install Python.Python.3.11
    winget install OpenJS.NodeJS
    winget install Git.Git
    ```
    *(Cierra y vuelve a abrir PowerShell después de instalar para que reconozca los comandos).*

## Paso 1: Descargar el Código
1.  Crea una carpeta en el Escritorio llamada `DKI`.
2.  Abre esa carpeta.
3.  Haz clic derecho en un espacio vacío > "Open in Terminal" (o "Abrir en Terminal").
4.  Escribe:
    ```powershell
    git clone <URL_DEL_REPOSITORIO> .
    ```
    *(Si tienes el archivo ZIP, descárgalo y descomprímelo en el Escritorio).*

## Paso 2: Configurar el Backend (Cerebro)
En la terminal (dentro de la carpeta DKI):

1.  **Entra a la carpeta backend**:
    ```powershell
    cd backend
    ```
2.  **Crea el entorno virtual**:
    ```powershell
    python -m venv .venv
    ```
3.  **Actívalo**:
    ```powershell
    .venv\Scripts\activate
    ```
    *(Si ves un error de permisos, ejecuta primero: `Set-ExecutionPolicy RemoteSigned -Scope CurrentUser` y luego intenta activar de nuevo).*
    *(Deberías ver `(.venv)` al principio de la línea).*

4.  **Instala librerías y prepara la base de datos**:
    ```powershell
    pip install -r requirements.txt
    python manage.py migrate
    ```
5.  **Arranca el servidor**:
    ```powershell
    python manage.py runserver
    ```

## Paso 3: Configurar el Frontend (Pantalla)
1.  Abre **otra** ventana de PowerShell/Terminal.
2.  Ve a la carpeta del proyecto y luego a `frontend`:
    ```powershell
    cd Desktop\DKI\frontend
    ```
3.  **Instala y arranca**:
    ```powershell
    npm install
    npm run dev
    ```

---

# 🍎 Opción B: MAC (macOS)

## Paso 0: Instalar Herramientas
Abre la Terminal (`Command + Espacio`, escribe "Terminal"):

1.  **Instalar Homebrew** (si no lo tienes):
    ```bash
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    ```
2.  **Instalar programas**:
    ```bash
    brew install python node git
    ```

## Paso 1: Descargar
```bash
cd Desktop
git clone <URL_DEL_REPOSITORIO> DKI
cd DKI
```

## Paso 2: Backend
```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

## Paso 3: Frontend
Abre una **nueva pestaña** de terminal (`Command + T`):
```bash
cd ~/Desktop/DKI/frontend
npm install
npm run dev
```

---

# 🚀 Cómo usar la aplicación (Todos)

Una vez que tengas ambas terminales corriendo sin errores:

1.  Abre tu navegador (Chrome, Edge, Safari).
2.  Entra a: **http://localhost:5173**

## 🔄 Resumen para el día a día

**Terminal 1 (Backend):**
*Windows:*
```powershell
cd Desktop\DKI\backend
.venv\Scripts\activate
python manage.py runserver
```
*Mac:*
```bash
cd ~/Desktop/DKI/backend
source .venv/bin/activate
python manage.py runserver
```

**Terminal 2 (Frontend):**
```bash
cd Desktop/DKI/frontend
npm run dev
```

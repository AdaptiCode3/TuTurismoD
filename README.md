# Tu-Turismo — Backend

Este repositorio contiene la API REST para el proyecto Tu-Turismo. 

Sigue estos pasos para configurar y ejecutar el proyecto en tu máquina local samy:

##  Instalar y Configurar en Local

1. **Clonar el repositorio e ir a la carpeta del backend:**
   ```bash
   cd PROJECT/back
   ```

2. **Crear y activar el entorno virtual:**
   * **En Windows (PowerShell):**
     ```powershell
     python -m venv venv
     .\venv\Scripts\Activate.ps1
     ```
   * **En Linux / macOS:**
     ```bash
     python3 -m venv venv
     source venv/bin/activate
     ```

3. **Instalar dependencias necesarias:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configurar variables de entorno (.env):**
   * Copia la plantilla de ejemplo:
     ```bash
     cp .env.example .env
     ```
   * Abre el archivo `.env` creado y solicita al equipo las credenciales del cluster de **MongoDB Atlas** para rellenar la variable `MONGO_URI`.

5. **Iniciar el servidor de desarrollo:**
   ```bash
   python manage.py runserver
   ```
   El servidor estará disponible en `http://localhost:8000/`.

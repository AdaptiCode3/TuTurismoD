# Tu-Turismo (Jalisco) — Backend

Este repositorio contiene la API REST backend para la plataforma de promoción turística integral del Estado de Jalisco, México: **Tu-Turismo**.

El proyecto está diseñado bajo un enfoque modular, limpio y desacoplado, haciendo uso de **Django 6.0** y **MongoDB (PyMongo)**.

---

## ⚠️ Restricción Arquitectónica Crítica
Este proyecto **NO utiliza el ORM relacional de Django** ni bases de datos relacionales tradicionales como PostgreSQL o SQLite.
*   `DATABASES` está vacío en `settings.py`.
*   Toda interacción con la base de datos se realiza de forma directa y optimizada mediante **PyMongo**.
*   **No se debe importar** `django.db.models` ni crear archivos de migración estándar.
*   Las validaciones y persistencia se gestionan a través del patrón **Singleton** (`core/database.py`) y clases de **Repositorio** específicas en cada módulo.

---

## 🛠️ Requisitos Previos
*   **Python 3.10 o superior**
*   **Instancia de MongoDB Atlas** (o local en su defecto) con una base de datos llamada `tuturismo_db`.
*   Acceso a la red (IP en la whitelist de Atlas).

---

## 🚀 Instalar y Configurar en Local

1.  **Clonar el repositorio y entrar a la carpeta del backend:**
    ```bash
    cd PROJECT/back
    ```

2.  **Crear e iniciar el entorno virtual (Virtual Environment):**
    *   **En Windows (PowerShell):**
        ```powershell
        python -m venv venv
        .\venv\Scripts\Activate.ps1
        ```
    *   **En Linux / macOS:**
        ```bash
        python3 -m venv venv
        source venv/bin/activate
        ```

3.  **Instalar dependencias requeridas:**
    ```bash
    pip install -r requirements.txt
    ```

4.  **Configurar variables de entorno:**
    Copia la plantilla de entorno:
    ```bash
    cp .env.example .env
    ```
    Abre `.env` en tu editor y sustituye las credenciales de MongoDB Atlas:
    ```env
    SECRET_KEY=clave_muy_segura_de_desarrollo
    DEBUG=True
    MONGO_URI=mongodb+srv://<usuario>:<password>@<cluster>.mongodb.net/?retryWrites=true&w=majority&appName=TuTurismo
    MONGO_DB_NAME=tuturismo_db
    ```

5.  **Correr el Servidor de Desarrollo:**
    ```bash
    python manage.py runserver
    ```
    El servidor iniciará en `http://localhost:8000/`.

---

## 🩺 Endpoints de Salud y Verificación
El backend provee un servicio de health-check integrado para validar la conectividad en tiempo real:

*   **Ruta:** `GET /api/v1/core/health/`
*   **Respuesta Exitosa (200 OK):**
    ```json
    {
      "django": "ok",
      "mongodb": "ok",
      "database": "tuturismo_db"
    }
    ```
*   **Error de Conexión (503 Service Unavailable):**
    ```json
    {
      "django": "ok",
      "mongodb": "unavailable",
      "error": "La base de datos MongoDB no está disponible. Verifica..."
    }
    ```

---

## 📂 Estructura del Código Core
*   [`core/database.py`](file:///c:/Users/jmy36/OneDrive/Documents/UNIVERSIDAD/INTEGRADOR%20III/TU-TURISMO-NOVENO/PROJECT/back/core/database.py): Implementa `MongoDBClient` usando el patrón Singleton para reutilizar de forma limpia el pool de conexiones TCP en cada petición HTTP de forma thread-safe.
*   [`core/views.py`](file:///c:/Users/jmy36/OneDrive/Documents/UNIVERSIDAD/INTEGRADOR%20III/TU-TURISMO-NOVENO/PROJECT/back/core/views.py): Contiene la lógica del endpoint de salud.
*   [`core/models.py`](file:///c:/Users/jmy36/OneDrive/Documents/UNIVERSIDAD/INTEGRADOR%20III/TU-TURISMO-NOVENO/PROJECT/back/core/models.py): Protegido y vacío con fines documentales para evitar el uso del ORM relacional.

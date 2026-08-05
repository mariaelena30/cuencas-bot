# 🌊 cuencas-bot

[![Python Version](https://shields.io)](https://python.org)
[![Platform](https://shields.io)](https://telegram.org)
[![Deploy](https://shields.io)](https://render.com)

Bot de Telegram diseñado para el monitoreo hidrológico en tiempo real de **4 cuencas críticas** de la Provincia del Chaco y zonas de influencia. El sistema evalúa los niveles de los ríos y clasifica automáticamente la gravedad de la situación mediante alertas visuales normalizadas.

---

## 🚦 Sistema de Alertas

El bot procesa las mediciones en metros y asigna un estado crítico según los umbrales paramétricos de cada localidad:

| Alerta | Estado | Descripción |
| :---: | :--- | :--- |
| 🟢 | **NORMAL** | Niveles operativos seguros. |
| 🟡 | **ALERTA** | El río alcanzó el umbral crítico de advertencia. |
| 🔴 | **EVACUACIÓN** | Nivel de desborde. Requiere despliegue de contingencia. |

> ⚠️ **Nota de Desarrollo**: El repositorio inicia con **datos semilla estáticos** (de demostración) definidos en `datos_cuencas.py`. Las cuencas están desacopladas para conectarse individualmente a sus fuentes oficiales o recibir actualizaciones mediante endpoints POST de una API externa.

---

## 🗺️ Cobertura del Monitoreo

### Cuencas Principales
*   **Río Paraná** (Estación Barranqueras)
*   **Río Paraguay** (Estación Puerto Bermejo / Confluencia)
*   **Río Bermejo** (Estación Presidencia de la Plaza)
*   **Río Pilcomayo** (Zona Norte de Chaco / Límite con Formosa)

### Localidades Registradas
El impacto hídrico se evalúa de forma diferenciada en los siguientes puntos debido a que el comportamiento del caudal varía según la geografía:
*   **Cuenca Paraná:** Resistencia, Barranqueras, Corrientes (Capital), Isla del Cerrito, Puerto Vilelas.
*   **Cuenca Paraguay:** Formosa (Capital), La Leonesa.
*   **Cuenca Bermejo:** Puerto Bermejo, Pampa del Indio, Villa Río Bermejito.
*   **Cuenca Pilcomayo:** El Sauzalito, Fuerte Esperanza.

---

## 🤖 Interfaz de Comandos del Bot

*   `/start` - Inicializa la interacción con el bot y comprueba la disponibilidad del servicio.
*   `/cuencas` - Devuelve un reporte resumido con el estado actual, nivel en metros y alerta visual de las 4 cuencas principales.

---

## 🛠️ Instalación y Configuración Local

### Prerrequisitos
*   Python 3.9 o superior instalado.
*   Un Token de API de Telegram obtenido mediante [@BotFather](https://t.me).

### Pasos de Configuración

1. **Clonar el repositorio y acceder al directorio:**
   ```bash
   cd cuencas_bot
   ```

2. **Crear y activar el entorno virtual:**
   ```bash
   python -m venv venv
   # En Linux / macOS:
   source venv/bin/activate
   # En Windows (CMD):
   venv\Scripts\activate
   ```

3. **Instalar dependencias y variables de entorno:**
   ```bash
   pip install -r requirements.txt
   cp .env.example .env
   ```

4. **Configurar el entorno:**
   Edita el archivo `.env` recién creado e introduce el token provisto por Telegram:
   ```env
   TELEGRAM_BOT_TOKEN="tu_token_secreto_aqui"
   ```

5. **Iniciar el bot:**
   ```bash
   python bot.py
   ```
   *Nota: Al utilizar la arquitectura **Long Polling**, el bot no requiere configuración de puertos locales ni túneles HTTP públicos (como Ngrok). Funciona directo en tu máquina.*

---

## ☁️ Despliegue en Producción (Render)

Este proyecto está diseñado para ejecutarse como un proceso continuo e independiente (*daemon*) en la nube:

1. Realiza un `git push` de tu repositorio a GitHub (comprueba que tu `.gitignore` esté ocultando correctamente el archivo `.env`).
2. En tu panel de **Render**, crea un nuevo **Background Worker**.
3. Conecta el repositorio de GitHub de este bot.
4. Completa la configuración del entorno con los siguientes comandos:
   *   **Build Command:** `pip install -r requirements.txt`
   *   **Start Command:** `python bot.py`
5. En la pestaña **Environment**, declara de forma segura la variable de producción:
   *   `TELEGRAM_BOT_TOKEN` = `[Tu Token Real de BotFather]`
6. Ejecuta el **Deploy**. El bot comenzará a escuchar eventos en Telegram de inmediato sin necesidad de gestionar certificados SSL o dominios web.

---

## 📈 Roadmap de Desarrollo

*   [ ] **Conexión en vivo:** Consumir los datos dinámicos mediante scraping o integración directa con la API del Instituto Nacional del Agua (INA) para las cuencas del Paraná y Paraguay.
*   [ ] **Alertas Push Automáticas:** Desarrollar un backend de persistencia (Base de Datos) para registrar los `chat_ids` de usuarios y ejecutar tareas programadas cron para notificar cambios abruptos de nivel.
*   [ ] **Centralización de Datos:** Integrar el bot con el archivo `main.py` (FastAPI) del dashboard de control para operar bajo una única fuente de verdad y eliminar la duplicación de datos en `datos_cuencas.py`.

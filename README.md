# 🌊 cuencas-bot

<p align="left">
  <img src="https://shields.io" alt="Python Version">
  <img src="https://shields.io" alt="Platform">
  <img src="https://shields.io" alt="Hosting">
</p>

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
   TFG_BOT_TOKEN="tu_token_secreto_aqui"


5. **Iniciar el bot:**
   ```bash
   python bot.py
   ```
   *Nota: Al utilizar la arquitectura **Long Polling**, el bot no requiere configuración de puertos locales ni túneles HTTP públicos (como Ngrok). Funciona directo en tu máquina.*

---

## ☁️ Opciones de Despliegue Permanente (24/7)

Al emplear mecanismos de escucha continua (*Polling*), el script requiere de un entorno que no se suspenda por inactividad. Se sugieren las siguientes alternativas de infraestructura:

### Opción A: Servidor Cloud Virtual (VPS) - Recomendado
Desplegar sobre una instancia cloud pequeña (Ubuntu/Debian) mediante herramientas de gestión persistente:
```bash
# Ejecutar en segundo plano mediante un multiplexor de terminales
tmux new -s cuencasbot
python bot.py
# Desacoplar presionando: Ctrl + B y luego D
```
*Alternativa profesional:* Configurar un servicio de sistema nativo mediante `systemd` para asegurar el reinicio automático del script tras fallas del sistema o reboots del servidor.

### Opción B: Plataformas PaaS con persistencia activa
Si se opta por proveedores administrados, se deben considerar alternativas que soporten procesos demonios estables de forma persistente sin ciclos de suspensión comerciales drásticos en sus planes de desarrollo.

---

## 📈 Roadmap de Desarrollo

*   [ ] **Conexión en vivo:** Consumir los datos dinámicos mediante scraping o integración directa con la API del Instituto Nacional del Agua (INA) para las cuencas del Paraná y Paraguay.
*   [ ] **Alertas Push Automáticas:** Desarrollar un backend de persistencia (Base de Datos) para registrar los `chat_ids` de usuarios y ejecutar tareas programadas cron para notificar cambios abruptos de nivel.
*   [ ] **Centralización de Datos:** Integrar el bot con el archivo `main.py` (FastAPI) del dashboard de control para operar bajo una única fuente de verdad y eliminar la duplicación de datos en `datos_cuencas.py`.

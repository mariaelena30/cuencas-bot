# cuencas-bot
# Bot de Telegram - Monitoreo 4 Cuencas Chaco

Bot que informa el estado de 4 cuencas (Paraná, Paraguay, Bermejo, Pilcomayo)
vía comandos de Telegram. Arranca con datos semilla claramente etiquetados
como demostración; cada cuenca se puede conectar a su fuente real de forma
independiente en `datos_cuencas.py`.

## 1. Crear el bot en Telegram

1. Hablar con [@BotFather](https://t.me/BotFather) en Telegram.
2. Mandar `/newbot`, elegir nombre y username (debe terminar en `bot`).
3. BotFather te da un token tipo `123456789:ABCdef...`. Guardalo, es secreto.

## 2. Probar en local

```bash
cd cuencas_bot
python -m venv venv
source venv/bin/activate  # en Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# editar .env y pegar el token real de BotFather
```

Para que el bot lea el `.env` automáticamente, instalar `python-dotenv`
(`pip install python-dotenv`) y agregar arriba de todo en `bot.py`:

```python
from dotenv import load_dotenv
load_dotenv()
```

O más simple, sin dotenv, exportar la variable antes de correr:

```bash
export TELEGRAM_BOT_TOKEN="pegar_token_aca"   # Windows: set TELEGRAM_BOT_TOKEN=...
python bot.py
```

Como usa **polling**, no necesita puerto ni URL pública — anda directo en
tu compu. Probalo hablándole al bot en Telegram con `/start`.

## 3. Desplegar en Render (background worker)

1. Subir esta carpeta a un repo de GitHub (el `.gitignore` ya excluye `.env`).
2. En Render: **New > Background Worker**.
3. Conectar el repo.
4. Build command: `pip install -r requirements.txt`
5. Start command: `python bot.py`
6. En **Environment**, agregar la variable `TELEGRAM_BOT_TOKEN` con el
   token real (nunca lo escribas en el código ni lo subas al repo).
7. Deploy. Con polling no hace falta configurar dominio ni puerto.

## Próximos pasos posibles

- Conectar Paraná y Paraguay a la API real del INA (tienen mejor cobertura).
- Agregar alertas automáticas push (requiere guardar chat_ids de usuarios
  suscriptos y un job periódico que compare niveles contra umbrales).
- Reusar el `main.py` (FastAPI) del proyecto del dashboard como fuente
  única de datos para bot + dashboard, en vez de duplicar `datos_cuencas.py`.

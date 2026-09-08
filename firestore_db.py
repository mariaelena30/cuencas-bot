"""
Conexion a Firestore para el ESTADO EN VIVO de cada localidad
(nivel_metros, velocidad de subida, ultima_verificacion, etc).

Los datos ESTATICOS (nombre, umbral_alerta, umbral_evacuacion, cuenca,
fuente) siguen viviendo en main.py como antes: casi no cambian y no
hace falta una lectura a la base de datos para eso.

POR QUE FIRESTORE Y NO EL DICCIONARIO EN MEMORIA:
Render (plan gratis) reinicia el proceso en cada deploy y cuando el
servicio se duerme por inactividad. Un diccionario en RAM se borra en
ese momento y vuelve a los valores semilla del codigo (esto es
exactamente lo que paso). Firestore persiste afuera del proceso: un
redeploy nunca vuelve a pisar una lectura real con un dato viejo.

CONFIGURACION NECESARIA (una sola vez, no hace falta repetirla):
1. En la consola de Firebase (el MISMO proyecto que ya usa el
   frontend de cuenca_chaco) -> icono de engranaje -> Configuracion
   del proyecto -> pestaña "Cuentas de servicio" -> boton
   "Generar nueva clave privada". Se descarga un archivo .json.
2. Copiar TODO el contenido de ese .json (es texto) y pegarlo como
   valor de una variable de entorno en Render llamada
   FIREBASE_CREDENTIALS_JSON (todo en una sola variable).
   ¡No subir ese .json al repo de GitHub bajo ningun concepto!
3. Agregar "firebase-admin" a requirements.txt del repo cuencas-bot.
"""
import json
import os

import firebase_admin
from firebase_admin import credentials, firestore

_db = None
COLECCION = "estado_localidades"


def get_db():
    """Inicializa Firestore una sola vez por proceso y reutiliza la conexion."""
    global _db
    if _db is not None:
        return _db

    credenciales_json = os.environ.get("FIREBASE_CREDENTIALS_JSON")
    if not credenciales_json:
        raise RuntimeError(
            "Falta la variable de entorno FIREBASE_CREDENTIALS_JSON en Render. "
            "Sin esto el backend no puede guardar datos reales de forma "
            "persistente (ver instrucciones arriba en este archivo)."
        )

    cred_dict = json.loads(credenciales_json)
    cred = credentials.Certificate(cred_dict)
    firebase_admin.initialize_app(cred)
    _db = firestore.client()
    return _db


def leer_estado(clave: str) -> dict | None:
    """Trae el ultimo estado real guardado de una localidad, o None si
    todavia no se guardo nunca (localidad nueva / primer arranque)."""
    doc = get_db().collection(COLECCION).document(clave).get()
    return doc.to_dict() if doc.exists else None


def guardar_estado(clave: str, datos: dict) -> None:
    """Guarda/actualiza el estado de una localidad.
    merge=True para no borrar campos que no se esten tocando ahora."""
    get_db().collection(COLECCION).document(clave).set(datos, merge=True)


# ---------------------------------------------------------------------
# NOTIFICACIONES PUSH (Firebase Cloud Messaging) - agregado 05/09/2026
#
# Guarda que celular/navegador quiere recibir alertas de que localidad,
# y manda el push con maxima prioridad cuando cambia de fase. Ver
# src/lib/pushNotifications.ts en el frontend para el lado que pide
# el permiso y guarda el token.
# ---------------------------------------------------------------------
COLECCION_TOKENS = "push_tokens"


def guardar_token_push(token: str, localidad: str) -> None:
    """Registra un token para recibir alertas de una localidad. Si el
    mismo token ya estaba anotado para otra localidad, se actualiza
    (una persona sigue una localidad a la vez, la mas reciente que
    eligio)."""
    get_db().collection(COLECCION_TOKENS).document(token).set(
        {"localidad": localidad, "activo": True}, merge=True
    )


def tokens_de_localidad(localidad: str) -> list[str]:
    """Todos los tokens activos suscriptos a una localidad puntual."""
    docs = (
        get_db()
        .collection(COLECCION_TOKENS)
        .where("localidad", "==", localidad)
        .where("activo", "==", True)
        .stream()
    )
    return [doc.id for doc in docs]


def desactivar_token(token: str) -> None:
    """Se llama cuando Firebase avisa que un token ya no es valido
    (la persona desinstalo la app, borro los datos del navegador,
    etc.) - evita seguir intentando mandarle push a un token muerto."""
    get_db().collection(COLECCION_TOKENS).document(token).set(
        {"activo": False}, merge=True
    )


def enviar_push_localidad(localidad: str, titulo: str, cuerpo: str, urgente: bool = True) -> dict:
    """
    Manda una notificacion push a TODOS los suscriptos de una
    localidad, con prioridad maxima (suena aunque el celular este en
    silencio - misma categoria que una alarma).

    Devuelve cuantos se mandaron OK y cuantos fallaron, para que quien
    llama (alertas_dispatcher.py) pueda registrarlo en el log.
    """
    from firebase_admin import messaging

    get_db()  # asegura que firebase_admin.initialize_app() ya corrio
    tokens = tokens_de_localidad(localidad)
    if not tokens:
        return {"enviados": 0, "fallidos": 0, "sin_suscriptores": True}

    mensaje = messaging.MulticastMessage(
        tokens=tokens,
        notification=messaging.Notification(title=titulo, body=cuerpo),
        data={"urgente": "true" if urgente else "false", "localidad": localidad},
        android=messaging.AndroidConfig(
            priority="high",  # entrega inmediata, no espera a que el celular "despierte" solo
            notification=messaging.AndroidNotification(
                priority="max",
                default_vibrate_timings=False,
                vibrate_timings_millis=[0, 500, 200, 500, 200, 500] if urgente else None,
                sound="default",
                visibility="public",  # se ve completa incluso en la pantalla bloqueada
            ),
        ),
        webpush=messaging.WebpushConfig(
            headers={"Urgency": "high"},
        ),
    )

    respuesta = messaging.send_multicast(mensaje)

    # Limpieza: si algun token quedo invalido (celular desinstalo la
    # app, etc.), lo desactivamos para no seguir intentando en vano.
    if respuesta.failure_count > 0:
        for idx, resultado in enumerate(respuesta.responses):
            if not resultado.success:
                desactivar_token(tokens[idx])

    return {"enviados": respuesta.success_count, "fallidos": respuesta.failure_count}


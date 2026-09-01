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

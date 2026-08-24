"""
actualizar_vertederos.py

Monitorea aperturas/cierres de los vertederos de Itaipu y Yacyreta
(represas sobre el rio Parana, aguas arriba de Chaco/Corrientes) como
INDICADOR DE ALERTA TEMPRANA: cuando abren compuertas por lluvias en
el sur de Brasil, el nivel del Parana en Corrientes/Barranqueras suele
subir unos dias despues. Complementa (no reemplaza) la medicion directa
de nivel en las estaciones de PNA.

POR QUE GOOGLE NEWS RSS Y NO SCRAPING DIRECTO:
itaipu.gov.py y eby.gov.py (Yacyreta) bloquean el acceso automatizado
en su robots.txt. Google News RSS agrega las coberturas de medios
(ABC Color, La Nacion PY, etc.) que SI cubren cada apertura/cierre,
y es un feed publico pensado para consumo automatizado.

LIMITACION HONESTA: esto es deteccion por palabras clave en titulares
de noticias, no un dato oficial estructurado. Puede haber falsos
negativos (si ningun medio cubre una apertura chica) o demora de
horas hasta que sale la nota. Sirve como alerta temprana adicional,
no como fuente unica de verdad.
"""

import json
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

# ---------------------------------------------------------------------
# CONFIGURACION
# ---------------------------------------------------------------------
REPRESAS = {
    "itaipu": {
        "nombre": "Itaipú",
        "query": "Itaipú vertedero OR compuertas",
        # Tiempo aproximado historico hasta que el efecto se nota en
        # Corrientes/Chaco. Es una REGLA DE DEDO basada en casos pasados
        # (ej. apertura del 1/nov/2023 -> alerta en Corrientes ~3-5 dias
        # despues), no un modelo hidraulico de propagacion de onda.
        "dias_hasta_corrientes_aprox": "4 a 7 dias",
    },
    "yacyreta": {
        "nombre": "Yacyretá",
        "query": "Yacyretá vertedero OR compuertas",
        # Yacyreta esta mucho mas cerca de Corrientes/Chaco que Itaipu
        # (aprox. 300km rio abajo vs. los mas de 600km de Itaipu), asi
        # que el efecto se siente mas rapido.
        "dias_hasta_corrientes_aprox": "1 a 3 dias",
    },
}

PALABRAS_APERTURA = ["abre", "abrió", "abrio", "reabre", "reabrió", "apertura", "abren"]
PALABRAS_CIERRE = ["cierra", "cerró", "cerro", "cierre", "cerraron"]

RUTA_SALIDA = "vertederos_estado.json"


def _fecha_rss(texto_fecha: str) -> datetime:
    try:
        return parsedate_to_datetime(texto_fecha)
    except (TypeError, ValueError):
        return datetime.now(timezone.utc)


def consultar_google_news(query: str, max_items: int = 15) -> list[dict]:
    """Trae los titulares mas recientes de Google News RSS para una consulta."""
    url = (
        "https://news.google.com/rss/search?"
        f"q={urllib.parse.quote(query)}&hl=es-419&gl=PY&ceid=PY:es"
    )
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (PortalHidricoChaco/1.0)"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        contenido = resp.read()

    raiz = ET.fromstring(contenido)
    items = []
    for item in raiz.findall(".//item")[:max_items]:
        titulo = item.findtext("title", default="")
        link = item.findtext("link", default="")
        fecha_txt = item.findtext("pubDate", default="")
        items.append({
            "titulo": titulo,
            "link": link,
            "fecha": _fecha_rss(fecha_txt).isoformat(),
        })
    return items


def clasificar_titular(titulo: str) -> str | None:
    """Devuelve 'APERTURA', 'CIERRE' o None segun palabras clave en el titulo."""
    titulo_lower = titulo.lower()

    # OJO: titulares tipo "ITAIPU no abrió las compuertas" contienen la
    # palabra "abrió" pero significan justo lo contrario (tranquilizador,
    # no es una apertura real). Sin este chequeo, se clasificaban mal.
    patrones_negacion = [
        r"\bno\s+abri[oó]\b", r"\bno\s+se\s+abri[oó]\b",
        r"\bno\s+abre\b", r"\bno\s+tiene\s+prevista\b",
        r"\bsin\s+apertura\b", r"\bno\s+habr[aá]\s+apertura\b",
    ]
    if any(re.search(p, titulo_lower) for p in patrones_negacion):
        return "CIERRE"  # se lee como "sigue sin verter", equivalente a estado cerrado/normal

    tiene_apertura = any(p in titulo_lower for p in PALABRAS_APERTURA)
    tiene_cierre = any(p in titulo_lower for p in PALABRAS_CIERRE)
    # Si el titular menciona ambas cosas (raro pero pasa en resumenes),
    # nos quedamos con la mas reciente por orden de aparicion en el texto.
    if tiene_apertura and not tiene_cierre:
        return "APERTURA"
    if tiene_cierre and not tiene_apertura:
        return "CIERRE"
    return None


def detectar_estado_represa(clave: str, config: dict) -> dict:
    """Busca noticias recientes y determina el estado actual (abierto/cerrado) de una represa."""
    try:
        noticias = consultar_google_news(config["query"])
    except Exception as e:
        return {
            "nombre": config["nombre"],
            "estado": "DESCONOCIDO",
            "error": f"No se pudo consultar noticias: {e}",
            "ultima_verificacion": datetime.now(timezone.utc).isoformat(),
        }

    eventos_clasificados = []
    for n in noticias:
        tipo = clasificar_titular(n["titulo"])
        if tipo:
            eventos_clasificados.append({**n, "tipo": tipo})

    if not eventos_clasificados:
        return {
            "nombre": config["nombre"],
            "estado": "SIN_NOTICIAS_RECIENTES",
            "detalle": "No se encontraron titulares recientes sobre apertura/cierre de vertedero.",
            "ultima_verificacion": datetime.now(timezone.utc).isoformat(),
        }

    # El evento mas reciente (por fecha de publicacion) define el estado actual
    eventos_clasificados.sort(key=lambda e: e["fecha"], reverse=True)
    evento_mas_reciente = eventos_clasificados[0]

    fecha_evento = datetime.fromisoformat(evento_mas_reciente["fecha"])
    dias_desde_evento = (datetime.now(timezone.utc) - fecha_evento).days

    return {
        "nombre": config["nombre"],
        "estado": "ABIERTO" if evento_mas_reciente["tipo"] == "APERTURA" else "CERRADO",
        "fecha_evento": evento_mas_reciente["fecha"],
        "dias_desde_evento": dias_desde_evento,
        "titular_fuente": evento_mas_reciente["titulo"],
        "link_fuente": evento_mas_reciente["link"],
        "dias_hasta_corrientes_aprox": config["dias_hasta_corrientes_aprox"],
        "ultima_verificacion": datetime.now(timezone.utc).isoformat(),
    }


def calcular_alerta_temprana(estados: dict) -> dict:
    """
    Si alguna represa esta ABIERTA y el evento fue reciente (menos de 15
    dias), genera una alerta temprana textual para mostrar en el dashboard.
    15 dias es un margen generoso: las aperturas duran de horas a semanas
    segun los casos historicos vistos, mejor pecar de cauteloso.
    """
    avisos = []
    for clave, info in estados.items():
        if info.get("estado") == "ABIERTO" and info.get("dias_desde_evento", 99) <= 15:
            avisos.append(
                f"{info['nombre']} abrió vertedero hace {info['dias_desde_evento']} día(s) "
                f"— posible subida del Paraná en Corrientes/Chaco en {info['dias_hasta_corrientes_aprox']}."
            )
    return {
        "hay_alerta": len(avisos) > 0,
        "avisos": avisos,
    }


def main():
    print("Consultando estado de vertederos (Itaipú, Yacyretá) via Google News...")
    estados = {}
    for clave, config in REPRESAS.items():
        estados[clave] = detectar_estado_represa(clave, config)
        estado_txt = estados[clave].get("estado", "?")
        print(f"  {config['nombre']}: {estado_txt}")

    alerta = calcular_alerta_temprana(estados)

    resultado = {
        "vertederos": estados,
        "alerta_temprana": alerta,
        "actualizado": datetime.now(timezone.utc).isoformat(),
    }

    with open(RUTA_SALIDA, "w", encoding="utf-8") as fh:
        json.dump(resultado, fh, ensure_ascii=False, indent=2)

    print(f"\n[OK] Guardado en {RUTA_SALIDA}")
    if alerta["hay_alerta"]:
        print("\n⚠️  ALERTA TEMPRANA:")
        for aviso in alerta["avisos"]:
            print(f"  - {aviso}")
    else:
        print("\nSin alertas tempranas activas por vertederos.")


if __name__ == "__main__":
    main()

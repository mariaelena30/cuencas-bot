"""
actualizar_nota_tecnica.py

Busca automaticamente la ULTIMA "Nota Tecnica Conjunta" sobre El Nino
publicada por UNNE / UFSM / APA Chaco en Zenodo, via la API publica de
Zenodo (developers.zenodo.org) - no hace falta scrapear ninguna pagina,
es una API REST pensada para esto.

Por que hace falta esto y no un link fijo:
Cada actualizacion del Observatorio UNNE-UFSM sale con un DOI de Zenodo
DISTINTO (Nota Tecnica N1, N2, N3, N4...). Un link fijo a la Nº3 queda
desactualizado en cuanto sale la Nº4. Este script busca por palabras
clave y siempre trae la mas reciente.
"""

import json
import re
import urllib.parse
import urllib.request
from datetime import datetime, timezone

ZENODO_API_URL = "https://zenodo.org/api/records"
QUERY = 'title:"Nota Técnica" AND title:"Chaco" AND title:"Niño"'
RUTA_SALIDA = "nota_tecnica_enso.json"


def buscar_nota_tecnica_mas_reciente() -> dict | None:
    """Consulta la API de Zenodo y devuelve el registro mas reciente que matchea la busqueda."""
    params = {
        "q": QUERY,
        "sort": "mostrecent",
        "size": "5",
    }
    url = f"{ZENODO_API_URL}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": "PortalHidricoChaco/1.0"})

    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read())

    hits = data.get("hits", {}).get("hits", [])
    if not hits:
        return None

    # Filtro extra por si la busqueda trae ruido: nos quedamos solo con
    # resultados que efectivamente mencionen "Nota Tecnica" en el titulo,
    # para no traer un paper cualquiera que use esas mismas palabras sueltas.
    candidatos = [h for h in hits if "nota técnica" in h["metadata"]["title"].lower()]
    if not candidatos:
        return None

    return candidatos[0]  # ya viene ordenado por mas reciente


def extraer_numero_nota(titulo: str) -> str | None:
    """De un titulo tipo 'NOTA TÉCNICA CONJUNTA Nº 3/2026...' extrae 'Nº 3/2026'."""
    match = re.search(r"N[º°]\s*\d+/\d{4}", titulo, re.IGNORECASE)
    return match.group(0) if match else None


def procesar_registro(registro: dict) -> dict:
    metadata = registro["metadata"]
    titulo = metadata.get("title", "")
    archivos = registro.get("files", [])
    pdf_url = archivos[0]["links"]["self"] if archivos else None

    return {
        "numero": extraer_numero_nota(titulo),
        "titulo": titulo,
        "descripcion": metadata.get("description", "")[:500],  # recorte, la descripcion completa es larga
        "fecha_publicacion": metadata.get("publication_date"),
        "doi": metadata.get("doi"),
        "url_doi": f"https://doi.org/{metadata.get('doi')}" if metadata.get("doi") else None,
        "url_pdf": pdf_url,
        "autores": [c.get("name") for c in metadata.get("creators", [])],
        "ultima_verificacion": datetime.now(timezone.utc).isoformat(),
    }


def main():
    print("Buscando la última Nota Técnica UNNE-UFSM-APA sobre El Niño en Zenodo...")
    try:
        registro = buscar_nota_tecnica_mas_reciente()
    except Exception as e:
        print(f"[ERROR] No se pudo consultar la API de Zenodo: {e}")
        resultado = {
            "encontrada": False,
            "error": str(e),
            "ultima_verificacion": datetime.now(timezone.utc).isoformat(),
        }
        with open(RUTA_SALIDA, "w", encoding="utf-8") as fh:
            json.dump(resultado, fh, ensure_ascii=False, indent=2)
        return

    if registro is None:
        print("No se encontró ninguna Nota Técnica todavía.")
        resultado = {"encontrada": False, "ultima_verificacion": datetime.now(timezone.utc).isoformat()}
    else:
        datos = procesar_registro(registro)
        resultado = {"encontrada": True, **datos}
        print(f"[OK] Encontrada: {datos['numero'] or '(sin número detectado)'}")
        print(f"     {datos['titulo']}")
        print(f"     DOI: {datos['url_doi']}")

    with open(RUTA_SALIDA, "w", encoding="utf-8") as fh:
        json.dump(resultado, fh, ensure_ascii=False, indent=2)
    print(f"\n[OK] Guardado en {RUTA_SALIDA}")


if __name__ == "__main__":
    main()

"""
obtener_precipitacion_cedei.py
--------------------------------
Portal Hidrico Chaco - Proyecto 2HC26

Lista las entradas mas recientes de precipitacion acumulada publicadas por
CEDEI (Ministerio de Produccion del Chaco), que se nutren de las 26
estaciones meteorologicas propias de la provincia.

CEDEI no tiene API formal: es un WordPress. Este script lista los posts
de la categoria "Precipitacion Acumulada Mensual" y extrae el link de
descarga de cada informe.

NOTA: el patron de busqueda del HTML es una primera aproximacion, no fue
verificado contra el HTML real del sitio. Si no encuentra entradas, hay
que ajustar PATRON_ENTRADA revisando el codigo fuente de la pagina.

Fuente: https://cedei.produccion.chaco.gov.ar/category/precipitaciones/precipitacion-acumulada-mensual/

Uso:
    python obtener_precipitacion_cedei.py
    python obtener_precipitacion_cedei.py --paginas 2
"""

import argparse
import csv
import re
import sys
from datetime import datetime
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError

BASE_URL = "https://cedei.produccion.chaco.gov.ar"
CATEGORIA_URL = f"{BASE_URL}/category/precipitaciones/precipitacion-acumulada-mensual/"

HEADERS = {"User-Agent": "PortalHidricoChaco/1.0 (+contacto proyecto 2HC26)"}

PATRON_ENTRADA = re.compile(
    r'<h2[^>]*class="[^"]*entry-title[^"]*"[^>]*>\s*<a[^>]*href="([^"]+)"[^>]*>([^<]+)</a>',
    re.IGNORECASE,
)

PATRON_DESCARGA = re.compile(
    r'<a[^>]*href="([^"]+\.(?:pdf|xlsx|xls|csv))"[^>]*>',
    re.IGNORECASE,
)


def descargar_pagina(url):
    req = Request(url, headers=HEADERS)
    try:
        with urlopen(req, timeout=20) as resp:
            return resp.read().decode("utf-8", errors="ignore")
    except HTTPError as e:
        print(f"[ERROR] HTTP {e.code} al pedir {url}", file=sys.stderr)
    except URLError as e:
        print(f"[ERROR] No se pudo conectar a {url}: {e.reason}", file=sys.stderr)
    return None


def listar_entradas(paginas=1):
    entradas = []
    for pagina in range(1, paginas + 1):
        url = CATEGORIA_URL if pagina == 1 else f"{CATEGORIA_URL}page/{pagina}/"
        html = descargar_pagina(url)
        if html is None:
            break
        encontradas = PATRON_ENTRADA.findall(html)
        if not encontradas:
            break
        for link, titulo in encontradas:
            entradas.append((titulo.strip(), link.strip()))
    return entradas


def buscar_link_descarga(url_entrada):
    html = descargar_pagina(url_entrada)
    if html is None:
        return None
    match = PATRON_DESCARGA.search(html)
    return match.group(1) if match else None


def main():
    parser = argparse.ArgumentParser(description="Precipitacion CEDEI - Portal Hidrico Chaco")
    parser.add_argument("--paginas", type=int, default=1)
    parser.add_argument("--con-descarga", action="store_true")
    parser.add_argument("--csv", default=None)
    args = parser.parse_args()

    entradas = listar_entradas(args.paginas)
    if not entradas:
        print("[AVISO] No se encontraron entradas. Puede que CEDEI haya cambiado "
              "la estructura del HTML - revisar PATRON_ENTRADA.", file=sys.stderr)
        sys.exit(1)

    filas = []
    print(f"Se encontraron {len(entradas)} informes de precipitacion:\n")
    for titulo, link in entradas:
        descarga = None
        if args.con_descarga:
            descarga = buscar_link_descarga(link)
        print(f"- {titulo}")
        print(f"  nota: {link}")
        if descarga:
            print(f"  descarga: {descarga}")
        filas.append({
            "titulo": titulo,
            "url_nota": link,
            "url_descarga": descarga or "",
            "consultado": datetime.now().isoformat(),
        })

    if args.csv:
        with open(args.csv, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=["titulo", "url_nota", "url_descarga", "consultado"])
            writer.writeheader()
            writer.writerows(filas)
        print(f"\n[OK] Guardado listado en {args.csv}")


if __name__ == "__main__":
    main()

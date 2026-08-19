"""
obtener_niveles_rios.py
------------------------
Portal Hidrico Chaco - Proyecto 2HC26

Obtiene los niveles hidrometricos en tiempo (casi) real del rio Parana y
Paraguay desde el API publico del CIMA (Centro de Investigaciones del Mar
y la Atmosfera, UBA/CONICET), y los relaciona con las 4 cuencas locales
que monitorea el proyecto: Bermejo, Rio de Oro, Tragadero y Negro-Salado.

Por que el nivel del Parana/Paraguay importa aunque monitoreemos cuencas
locales: cuando el Parana esta alto, actua como un "tapon" que impide que
los rios/riachos locales (Tragadero, Negro-Salado, Rio de Oro, Bermejo)
drenen bien, generando anegamiento aguas arriba de la desembocadura -
independientemente de si llovio localmente o no. Por eso el pipeline debe
cruzar SIEMPRE altura del Parana + estado de la cuenca local.

Fuente: https://bermejo.cima.fcen.uba.ar/php/get_rios.php
(Sin autenticacion, JSON publico, actualizacion diaria)

Uso:
    python obtener_niveles_rios.py
    python obtener_niveles_rios.py --formato csv
"""

import argparse
import csv
import json
import sys
from datetime import datetime, timezone
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError

API_URL = "https://bermejo.cima.fcen.uba.ar/php/get_rios.php"

PUERTO_A_CUENCA = {
    "Barranqueras": "Tragadero / Negro-Salado",
    "Corrientes":   "Referencia regional (margen opuesta)",
    "Bermejo":      "Cuenca del Rio Bermejo",
    "Formosa":      "Referencia regional (Rio Paraguay)",
    "Empedrado":    "Referencia regional aguas abajo",
    "Goya":         "Referencia regional aguas abajo",
    "Bella Vista":  "Referencia regional aguas abajo",
    "Paso de la Patria": "Referencia regional (cercano a confluencia "
                         "Parana-Paraguay)",
}

CAMPOS_SALIDA = [
    "timestamp_consulta",
    "puerto",
    "rio",
    "altura_actual_m",
    "altura_anterior_m",
    "tendencia",
    "nivel_alerta_m",
    "nivel_evacuacion_m",
    "distancia_a_alerta_m",
    "cuenca_relacionada",
]


def obtener_datos_crudos():
    req = Request(API_URL, headers={"User-Agent": "PortalHidricoChaco/1.0"})
    try:
        with urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return data
    except HTTPError as e:
        print(f"[ERROR] El servidor respondio con error HTTP {e.code}", file=sys.stderr)
    except URLError as e:
        print(f"[ERROR] No se pudo conectar al API: {e.reason}", file=sys.stderr)
    except json.JSONDecodeError:
        print("[ERROR] La respuesta no es JSON valido", file=sys.stderr)
    return None


def procesar_estaciones(data_cruda):
    ahora = datetime.now(timezone.utc).isoformat()
    filas = []

    for est in data_cruda:
        puerto = est.get("puerto", "").strip()
        rio = est.get("rio", "").strip()

        altura_str = est.get("altura", "").strip()
        altura_ant_str = est.get("alturaAnt", "").strip()

        try:
            altura = float(altura_str) if altura_str else None
        except ValueError:
            altura = None
        try:
            altura_ant = float(altura_ant_str) if altura_ant_str else None
        except ValueError:
            altura_ant = None

        alerta = float(est.get("alerta", 0) or 0)
        evacuacion = float(est.get("evacuacion", 0) or 0)

        if altura is not None and altura_ant is not None:
            diff = round(altura - altura_ant, 2)
            if diff > 0.01:
                tendencia = f"subiendo (+{diff} m)"
            elif diff < -0.01:
                tendencia = f"bajando ({diff} m)"
            else:
                tendencia = "estable"
        else:
            tendencia = "sin dato"

        distancia_alerta = round(alerta - altura, 2) if altura is not None else None

        filas.append({
            "timestamp_consulta": ahora,
            "puerto": puerto,
            "rio": rio,
            "altura_actual_m": altura,
            "altura_anterior_m": altura_ant,
            "tendencia": tendencia,
            "nivel_alerta_m": alerta,
            "nivel_evacuacion_m": evacuacion,
            "distancia_a_alerta_m": distancia_alerta,
            "cuenca_relacionada": PUERTO_A_CUENCA.get(puerto, "Sin asociar"),
        })

    return filas


def imprimir_resumen(filas):
    print("=" * 78)
    print(f"PORTAL HIDRICO CHACO - Niveles Parana/Paraguay ({datetime.now().strftime('%d/%m/%Y %H:%M')})")
    print("=" * 78)
    for f in filas:
        if f["cuenca_relacionada"] == "Sin asociar":
            continue
        altura = f["altura_actual_m"]
        altura_txt = f"{altura:.2f} m" if altura is not None else "SIN DATO"
        print(f"- {f['puerto']:<18} ({f['rio']:<9}) | altura: {altura_txt:<10} "
              f"| {f['tendencia']:<18} | cuenca: {f['cuenca_relacionada']}")
    print("-" * 78)
    print("Resto de estaciones (referencia regional):")
    for f in filas:
        if f["cuenca_relacionada"] != "Sin asociar" and "Referencia" not in f["cuenca_relacionada"]:
            continue
        altura = f["altura_actual_m"]
        altura_txt = f"{altura:.2f} m" if altura is not None else "SIN DATO"
        print(f"  {f['puerto']:<18} ({f['rio']:<9}) | altura: {altura_txt:<10} | {f['tendencia']}")
    print("=" * 78)


def guardar_csv(filas, ruta="niveles_rios.csv"):
    with open(ruta, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=CAMPOS_SALIDA)
        writer.writeheader()
        writer.writerows(filas)
    print(f"[OK] Guardado en {ruta}")


def main():
    parser = argparse.ArgumentParser(description="Niveles Parana/Paraguay - Portal Hidrico Chaco")
    parser.add_argument("--formato", choices=["texto", "csv", "json"], default="texto")
    parser.add_argument("--salida", default="niveles_rios.csv", help="Ruta del archivo de salida (csv/json)")
    args = parser.parse_args()

    data_cruda = obtener_datos_crudos()
    if data_cruda is None:
        sys.exit(1)

        filas = procesar_estaciones(data_cruda)
    publicar_al_backend(filas)
    if args.formato == "texto":
        imprimir_resumen(filas)
    elif args.formato == "csv":
        guardar_csv(filas, args.salida)
    elif args.formato == "json":
        with open(args.salida.replace(".csv", ".json"), "w", encoding="utf-8") as fh:
            json.dump(filas, fh, ensure_ascii=False, indent=2)
        print(f"[OK] Guardado en {args.salida.replace('.csv', '.json')}")

BACKEND_URL = "https://cuencas-bot.onrender.com"

MAPEO_PUERTO_A_LOCALIDAD = {
    "Barranqueras": ["barranqueras", "resistencia", "puerto_vilelas"],
    "Corrientes": ["corrientes"],
    "Formosa": ["formosa"],
    "Bermejo": ["puerto_bermejo"],
}

def publicar_al_backend(filas):
    import requests
    for f in filas:
        puerto = f["puerto"]
        altura = f["altura_actual_m"]
        if altura is None or puerto not in MAPEO_PUERTO_A_LOCALIDAD:
            continue
        for localidad in MAPEO_PUERTO_A_LOCALIDAD[puerto]:
            try:
                r = requests.post(
                    f"{BACKEND_URL}/hidrologia/actualizar",
                    json={"localidad": localidad, "nivel_metros": altura},
                    timeout=15.0,
                )
                print(f"{puerto} -> {localidad}: {altura} m (status {r.status_code})")
            except Exception as e:
                print(f"[ERROR] {localidad}: {e}")
if __name__ == "__main__":
    main()

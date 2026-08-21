"""
obtener_niveles_rios.py
------------------------
Portal Hidrico Chaco - Proyecto 2HC26

Obtiene los niveles hidrometricos en tiempo (casi) real del rio Parana y
Paraguay desde el API publico del CIMA (Centro de Investigaciones del Mar
y la Atmosfera, UBA/CONICET).

Relaciona las estaciones con las cuencas/localidades monitoreadas
por el proyecto Portal Hidrico Chaco.

Fuente:
https://bermejo.cima.fcen.uba.ar/php/get_rios.php

Uso:
    python obtener_niveles_rios.py
    python obtener_niveles_rios.py --formato csv
    python obtener_niveles_rios.py --formato json
"""

import argparse
import csv
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError


# ============================================================
# CONFIGURACION
# ============================================================

API_URL = "https://bermejo.cima.fcen.uba.ar/php/get_rios.php"

BACKEND_URL = "https://cuencas-bot.onrender.com"


# ============================================================
# RELACION PUERTO -> CUENCA
# ============================================================

PUERTO_A_CUENCA = {
    "Barranqueras": "Tragadero / Negro-Salado",
    "Corrientes": "Referencia regional (margen opuesta)",
    "Bermejo": "Cuenca del Rio Bermejo",
    "Formosa": "Referencia regional (Rio Paraguay)",
    "Empedrado": "Referencia regional aguas abajo",
    "Goya": "Referencia regional aguas abajo",
    "Bella Vista": "Referencia regional aguas abajo",
    "Paso de la Patria": (
        "Referencia regional (cercano a confluencia "
        "Parana-Paraguay)"
    ),
}


# ============================================================
# RELACION PUERTO -> LOCALIDADES DEL BACKEND
# ============================================================

MAPEO_PUERTO_A_LOCALIDAD = {
    "Barranqueras": [
        "barranqueras",
        "resistencia",
        "puerto_vilelas",
    ],
    "Corrientes": [
        "corrientes",
    ],
    "Formosa": [
        "formosa",
    ],
    "Bermejo": [
        "puerto_bermejo",
    ],
}


# ============================================================
# CAMPOS DE SALIDA
# ============================================================

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


# ============================================================
# OBTENER DATOS DEL API DEL CIMA
# ============================================================

def obtener_datos_crudos():
    req = Request(
        API_URL,
        headers={
            "User-Agent": "PortalHidricoChaco/1.0"
        },
    )

    try:
        with urlopen(req, timeout=60.0) as resp:
            data = json.loads(
                resp.read().decode("utf-8")
            )

        return data

    except HTTPError as e:
        print(
            f"[ERROR] El servidor respondio con error HTTP {e.code}",
            file=sys.stderr,
        )

    except URLError as e:
        print(
            f"[ERROR] No se pudo conectar al API: {e.reason}",
            file=sys.stderr,
        )

    except json.JSONDecodeError:
        print(
            "[ERROR] La respuesta no es JSON valido",
            file=sys.stderr,
        )

    return None


# ============================================================
# PROCESAR ESTACIONES
# ============================================================

def procesar_estaciones(data_cruda):

    ahora = datetime.now(timezone.utc).isoformat()

    filas = []

    for est in data_cruda:

        puerto = est.get(
            "puerto",
            ""
        ).strip()

        rio = est.get(
            "rio",
            ""
        ).strip()

        altura_str = est.get(
            "altura",
            ""
        ).strip()

        altura_ant_str = est.get(
            "alturaAnt",
            ""
        ).strip()

        # ----------------------------------------------------
        # ALTURA ACTUAL
        # ----------------------------------------------------

        try:
            altura = (
                float(altura_str)
                if altura_str
                else None
            )

        except ValueError:
            altura = None

        # ----------------------------------------------------
        # ALTURA ANTERIOR
        # ----------------------------------------------------

        try:
            altura_ant = (
                float(altura_ant_str)
                if altura_ant_str
                else None
            )

        except ValueError:
            altura_ant = None

        # ----------------------------------------------------
        # NIVELES DE ALERTA Y EVACUACION
        # ----------------------------------------------------

        try:
            alerta = float(
                est.get("alerta", 0) or 0
            )

        except (ValueError, TypeError):
            alerta = 0

        try:
            evacuacion = float(
                est.get("evacuacion", 0) or 0
            )

        except (ValueError, TypeError):
            evacuacion = 0

        # ----------------------------------------------------
        # CALCULAR TENDENCIA
        # ----------------------------------------------------

        if altura is not None and altura_ant is not None:

            diff = round(
                altura - altura_ant,
                2
            )

            if diff > 0.01:
                tendencia = (
                    f"subiendo (+{diff} m)"
                )

            elif diff < -0.01:
                tendencia = (
                    f"bajando ({diff} m)"
                )

            else:
                tendencia = "estable"

        else:
            tendencia = "sin dato"

        # ----------------------------------------------------
        # DISTANCIA AL NIVEL DE ALERTA
        # ----------------------------------------------------

        if altura is not None:
            distancia_alerta = round(
                alerta - altura,
                2
            )
        else:
            distancia_alerta = None

        # ----------------------------------------------------
        # AGREGAR FILA
        # ----------------------------------------------------

        filas.append(
            {
                "timestamp_consulta": ahora,
                "puerto": puerto,
                "rio": rio,
                "altura_actual_m": altura,
                "altura_anterior_m": altura_ant,
                "tendencia": tendencia,
                "nivel_alerta_m": alerta,
                "nivel_evacuacion_m": evacuacion,
                "distancia_a_alerta_m": distancia_alerta,
                "cuenca_relacionada": PUERTO_A_CUENCA.get(
                    puerto,
                    "Sin asociar",
                ),
            }
        )

    return filas


# ============================================================
# MOSTRAR RESUMEN EN CONSOLA
# ============================================================

def imprimir_resumen(filas):

    print("=" * 78)

    print(
        "PORTAL HIDRICO CHACO - "
        "Niveles Parana/Paraguay "
        f"({datetime.now().strftime('%d/%m/%Y %H:%M')})"
    )

    print("=" * 78)

    # --------------------------------------------------------
    # ESTACIONES RELACIONADAS CON CUENCAS LOCALES
    # --------------------------------------------------------

    for f in filas:

        cuenca = f["cuenca_relacionada"]

        if (
            cuenca == "Sin asociar"
            or "Referencia" in cuenca
        ):
            continue

        altura = f["altura_actual_m"]

        if altura is not None:
            altura_txt = f"{altura:.2f} m"
        else:
            altura_txt = "SIN DATO"

        print(
            f"- {f['puerto']:<18} "
            f"({f['rio']:<9}) | "
            f"altura: {altura_txt:<10} | "
            f"{f['tendencia']:<18} | "
            f"cuenca: {cuenca}"
        )

    print("-" * 78)

    # --------------------------------------------------------
    # ESTACIONES DE REFERENCIA REGIONAL
    # --------------------------------------------------------

    print(
        "Resto de estaciones "
        "(referencia regional):"
    )

    for f in filas:

        cuenca = f["cuenca_relacionada"]

        if (
            cuenca != "Sin asociar"
            and "Referencia" not in cuenca
        ):
            continue

        altura = f["altura_actual_m"]

        if altura is not None:
            altura_txt = f"{altura:.2f} m"
        else:
            altura_txt = "SIN DATO"

        print(
            f"  {f['puerto']:<18} "
            f"({f['rio']:<9}) | "
            f"altura: {altura_txt:<10} | "
            f"{f['tendencia']}"
        )

    print("=" * 78)


# ============================================================
# GUARDAR CSV
# ============================================================

def guardar_csv(
    filas,
    ruta="niveles_rios.csv",
):

    with open(
        ruta,
        "w",
        newline="",
        encoding="utf-8",
    ) as fh:

        writer = csv.DictWriter(
            fh,
            fieldnames=CAMPOS_SALIDA,
        )

        writer.writeheader()

        writer.writerows(filas)

    print(
        f"[OK] Guardado en {ruta}"
    )


# ============================================================
# PUBLICAR DATOS EN EL BACKEND
# ============================================================

def publicar_al_backend(filas):

    import requests

    print()
    print("=" * 78)
    print("PUBLICANDO DATOS EN BACKEND")
    print("=" * 78)

    for f in filas:

        puerto = f["puerto"]

        altura = f["altura_actual_m"]

        # ----------------------------------------------------
        # IGNORAR SI NO HAY ALTURA
        # ----------------------------------------------------

        if altura is None:
            continue

        # ----------------------------------------------------
        # IGNORAR PUERTOS SIN LOCALIDAD CONFIGURADA
        # ----------------------------------------------------

        if puerto not in MAPEO_PUERTO_A_LOCALIDAD:
            continue

        # ----------------------------------------------------
        # PUBLICAR EN CADA LOCALIDAD
        # ----------------------------------------------------

        for localidad in MAPEO_PUERTO_A_LOCALIDAD[puerto]:

            try:

                r = requests.post(
                    f"{BACKEND_URL}/hidrologia/actualizar",
                    json={
                        "localidad": localidad,
                        "nivel_metros": altura,
                    },
                    timeout=35.0,
                )

                print(
                    f"{puerto} -> "
                    f"{localidad}: "
                    f"{altura} m "
                    f"(status {r.status_code})"
                )

            except Exception as e:

                print(
                    f"[ERROR] "
                    f"{localidad}: {e}"
                )

    print("=" * 78)


# ============================================================
# GUARDAR JSON EN MODO HISTORICO (append, no overwrite)
# ============================================================

def guardar_json_historico(filas, ruta="niveles_rios.json", dias_a_conservar=60):
    """
    Antes esto sobrescribia niveles_rios.json en cada corrida, asi que
    calcular_tendencia.py nunca tenia mas de una lectura para trabajar.
    Ahora: lee el historico existente, le agrega las lecturas nuevas de
    esta corrida, y guarda todo junto. Recorta lecturas mas viejas que
    `dias_a_conservar` para que el archivo no crezca para siempre
    (con 4 corridas/dia via el workflow de cada 6hs, 60 dias son
    unas pocas miles de filas - nada que rompa el repo).
    """
    historico = []
    if os.path.exists(ruta):
        try:
            with open(ruta, "r", encoding="utf-8") as fh:
                contenido = json.load(fh)
            if isinstance(contenido, list):
                historico = contenido
        except (json.JSONDecodeError, OSError) as e:
            print(f"[AVISO] No se pudo leer el historico existente ({e}), se arranca uno nuevo.")

    historico.extend(filas)

    limite = datetime.now(timezone.utc) - timedelta(days=dias_a_conservar)

    def _es_reciente(fila):
        try:
            fecha = datetime.fromisoformat(fila["timestamp_consulta"].replace("Z", "+00:00"))
            if fecha.tzinfo is None:
                fecha = fecha.replace(tzinfo=timezone.utc)
            return fecha >= limite
        except (KeyError, ValueError, TypeError, AttributeError):
            return True  # si no se puede leer la fecha, no se descarta por las dudas

    historico = [f for f in historico if _es_reciente(f)]

    with open(ruta, "w", encoding="utf-8") as fh:
        json.dump(historico, fh, ensure_ascii=False, indent=2)

    print(f"[OK] Historico actualizado en {ruta}: {len(historico)} lecturas guardadas "
          f"(se conservan los ultimos {dias_a_conservar} dias).")


# ============================================================
# FUNCION PRINCIPAL
# ============================================================

def main():

    parser = argparse.ArgumentParser(
        description=(
            "Niveles Parana/Paraguay - "
            "Portal Hidrico Chaco"
        )
    )

    parser.add_argument(
        "--formato",
        choices=[
            "texto",
            "csv",
            "json",
        ],
        default="texto",
    )

    parser.add_argument(
        "--salida",
        default="niveles_rios.csv",
        help=(
            "Ruta del archivo de salida "
            "(csv/json)"
        ),
    )

    args = parser.parse_args()

    # --------------------------------------------------------
    # 1. OBTENER DATOS
    # --------------------------------------------------------

    print(
        "[1/4] Consultando API del CIMA..."
    )

    data_cruda = obtener_datos_crudos()

    if data_cruda is None:
        print(
            "[ERROR] No se pudieron obtener "
            "los datos."
        )
        sys.exit(1)

    print(
        "[OK] Datos obtenidos correctamente."
    )

    # --------------------------------------------------------
    # 2. PROCESAR ESTACIONES
    # --------------------------------------------------------

    print(
        "[2/4] Procesando estaciones..."
    )

    filas = procesar_estaciones(
        data_cruda
    )

    print(
        f"[OK] {len(filas)} estaciones procesadas."
    )

    # --------------------------------------------------------
    # 3. PUBLICAR EN BACKEND
    # --------------------------------------------------------

    print(
        "[3/4] Publicando datos en backend..."
    )

    publicar_al_backend(
        filas
    )

    # --------------------------------------------------------
    # 4. GENERAR SALIDA
    # --------------------------------------------------------

    print(
        "[4/4] Generando salida..."
    )

    if args.formato == "texto":

        imprimir_resumen(
            filas
        )

    elif args.formato == "csv":

        guardar_csv(
            filas,
            args.salida,
        )

    elif args.formato == "json":

        ruta_json = args.salida.replace(
            ".csv",
            ".json",
        )

        guardar_json_historico(filas, ruta_json)


# ============================================================
# PUNTO DE ENTRADA
# ============================================================

if __name__ == "__main__":
    main()

"""
defensas_amgr.py
------------------------
Portal Hidrico Chaco

Cotas de referencia del sistema de defensas contra inundaciones del
Area Metropolitana del Gran Resistencia (AMGR): Resistencia, Barranqueras,
Puerto Vilelas y Fontana.

Fuentes:
- Roces, C. "La ciudad de Resistencia y las inundaciones. La efectividad
  del sistema de defensas empleado." UNNE, Trabajo Final de Carrera.
- Depettris, C.; Rohrmann, H.; Martinez, L.; Ruberto, A.; Gomez, M.
  "Aprovechamiento de un sistema lagunar regulador de excesos pluviales
  en areas densamente pobladas." UNNE.
- Resoluciones N 1111/98 y 303/09 de la Administracion Provincial del
  Agua (APA) del Chaco: fijan cota de linea de ribera y linea de
  restriccion severa de las lagunas del AMGR.

IMPORTANTE: estas cotas son las del sistema general de defensas del
AMGR. Fuera de esta zona (Bermejo, Pilcomayo, localidades sin datos
verificados) NO hay que asumir estos valores: usar None y marcar
"sin_confirmar" hasta conseguir la fuente oficial (APA / Defensa Civil).
"""

# ============================================================
# COTA DE REFERENCIA MOP (Ministerio de Obras Publicas)
# ============================================================
# El "cero" de estas cotas es el sistema MOP usado historicamente
# en los estudios del AMGR. No confundir con cotas IGN/elipsoidales.

DEFENSA_PERIMETRAL_AMGR = {
    "descripcion": "Terraplen perimetral que protege al AMGR",
    "cota_terraplen_m_mop": 52.00,
    "fuente": "Roces (UNNE) - MOP, inundacion maxima registrada 1982-1983 (50.50 m MOP)",
}

LIMITE_OPERATIVO_BARRANQUERAS = {
    "descripcion": (
        "Nivel del riacho Barranqueras a partir del cual el sistema "
        "de defensas actual queda al limite de su capacidad (evacuacion "
        "total prevista en 1998 con este umbral)"
    ),
    "nivel_riacho_m": 9.50,
    "fuente": "Roces (UNNE), citando evento de 1998",
}

RIO_NEGRO_LINEA_RIBERA = {
    "descripcion": "Linea de ribera del Rio Negro dentro del recinto defendido",
    "cota_m_mop": 48.53,
    "fuente": "Roces (UNNE)",
}

# ============================================================
# LAGUNAS INTERNAS DEL RECINTO (regulan excedentes pluviales)
# ============================================================
# Segun Roces (UNNE): quedan ~20 lagunas dentro del recinto de
# defensas, con linea de ribera general en 48.08 m MOP.
# Depettris et al. dan el detalle de las lagunas del sistema
# Arguello-Navarro-Prosperidad con resoluciones APA especificas.

LAGUNAS_AMGR = {
    "linea_ribera_general_m_mop": 48.08,
    "fuente_general": "Roces (UNNE)",
    "sistema_arguello_navarro_prosperidad": {
        "area_aporte_ha": 660,
        "resoluciones_apa": ["1111/98", "303/09"],
        "descripcion": (
            "Fijan cota de linea de ribera y linea de restriccion severa "
            "para las lagunas comprendidas en el AMGR. Estacion de bombeo "
            "trasvasa excesos pluviales al lado externo (Rio Negro) cuando "
            "este esta por debajo del nivel de las lagunas."
        ),
        "fuente": "Depettris, Rohrmann, Martinez, Ruberto, Gomez (UNNE)",
        # TODO: pedir a APA Chaco (cuando el sitio vuelva a estar online)
        # las cotas MOP puntuales de cada resolucion, hoy solo tenemos
        # la referencia bibliografica, no el numero exacto de cada una.
    },
    "laguna_avalos": {
        "descripcion": "Eje principal de desagues pluviales del area de mayor densidad de Resistencia",
        "fuente": "Jornadas Divulgacion Cientifica UNNE 2021",
        "cota_m_mop": None,  # sin confirmar todavia
    },
}

# ============================================================
# SUBCUENCAS PLUVIALES CON MODELACION HEC-1 EXISTENTE
# ============================================================
# Estas subcuencas tienen mancha de inundacion ya calculada por
# UNNE (no HEC-RAS, es HEC-1, mas viejo, pero es dato real y citable).

SUBCUENCAS_MODELADAS = {
    "villa_los_lirios": {
        "fuente": "Bravo & Pilar (2003), UNNE",
    },
    "wilde_pueyrredon": {
        "fuente": "Bravo, Bianucci, Pilar, Depettris (2004), UNNE",
    },
    "hernandarias": {
        "fuente": "Bravo, Bianucci, Pilar, Depettris (2004), UNNE",
    },
}

# ============================================================
# LOCALIDADES FUERA DEL AMGR CON ESTUDIO DE RIESGO HIDRICO PROPIO
# ============================================================
# No comparten las cotas del AMGR. Cada una tiene su propio estudio
# citable, pero sin cotas MOP verificadas todavia.

OTRAS_LOCALIDADES_CON_ESTUDIO = {
    "general_jose_de_san_martin": {
        "fuente": "Meza & Ramirez (2018), UNNE - identificacion de areas con riesgo",
    },
    "puerto_vilelas": {
        "fuente": "Estudio de vulnerabilidad ante inundacion pluvial y fluvial, UNNE",
    },
    "corrientes_capital": {
        "fuente": "Beca doctoral CONICET-UNNE - areas ribereñas vulnerables",
    },
}


def get_defensa_por_localidad(localidad: str):
    """
    Devuelve la cota de defensa aplicable a una localidad del AMGR,
    o None si la localidad esta fuera del AMGR / sin datos verificados.
    Usar SIEMPRE esta funcion en vez de hardcodear 52.00 o 9.50 en
    otros archivos, para no repetir el numero en 5 lugares distintos.
    """
    amgr = {"resistencia", "barranqueras", "puerto_vilelas", "fontana"}
    if localidad.lower() in amgr:
        return {
            "cota_terraplen_m_mop": DEFENSA_PERIMETRAL_AMGR["cota_terraplen_m_mop"],
            "limite_operativo_barranqueras_m": LIMITE_OPERATIVO_BARRANQUERAS["nivel_riacho_m"],
        }
    return None

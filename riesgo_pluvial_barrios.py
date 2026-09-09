"""
riesgo_pluvial_barrios.py
------------------------
Portal Hidrico Chaco

Marca barrios con riesgo de anegamiento por LLUVIA (pluvial), que es
un criterio distinto al de RENABAP (que identifica asentamientos
informales, no riesgo hidrico). Un barrio puede tener riesgo pluvial
sin ser informal, y viceversa.

Esto es un PRIMER borrador basado en las zonas mencionadas en la
bibliografia UNNE (lagunas internas del AMGR + subcuencas con
modelacion HEC-1 existente). NO es un cruce GIS completo todavia.
Cuando se consiga el DEM (IGN o ALOS PALSAR via search.asf.alaska.edu)
y el shapefile de barrios, reemplazar esta lista manual por el
resultado del cruce en QGIS (Vectorial > Analisis > Interseccion).

Ver defensas_amgr.py para las fuentes completas de cada zona.
"""

from defensas_amgr import LAGUNAS_AMGR, SUBCUENCAS_MODELADAS

# ============================================================
# BARRIOS/ZONAS CON RESPALDO BIBLIOGRAFICO DE RIESGO PLUVIAL
# ============================================================
# Confianza "alta": zona citada explicitamente en un estudio UNNE.
# Confianza "sin_confirmar": mencionada en prensa/anecdotico, falta
# fuente tecnica. Nunca se muestra como dato duro sin esta etiqueta.

BARRIOS_RIESGO_PLUVIAL = [
    {
        "zona": "villa_los_lirios",
        "riesgo_pluvial": True,
        "confianza": "alta",
        "motivo": "Subcuenca con modelacion HEC-1 (Bravo & Pilar, 2003)",
    },
    {
        "zona": "area_laguna_avalos",
        "riesgo_pluvial": True,
        "confianza": "alta",
        "motivo": "Eje principal de desagues pluviales de mayor densidad poblacional",
    },
    {
        "zona": "area_lagunas_arguello_navarro_prosperidad",
        "riesgo_pluvial": True,
        "confianza": "alta",
        "motivo": "Sistema lagunar regulador de excedentes pluviales, area de aporte 660 ha",
    },
    {
        "zona": "subcuenca_wilde_pueyrredon",
        "riesgo_pluvial": True,
        "confianza": "alta",
        "motivo": "Mancha de inundacion modelada con HEC-1 (2004)",
    },
    {
        "zona": "subcuenca_hernandarias",
        "riesgo_pluvial": True,
        "confianza": "alta",
        "motivo": "Mancha de inundacion modelada con HEC-1 (2004)",
    },
    {
        "zona": "puerto_vilelas",
        "riesgo_pluvial": True,
        "confianza": "alta",
        "motivo": "Estudio de vulnerabilidad ante inundacion pluvial y fluvial (UNNE)",
    },
    {
        "zona": "general_jose_de_san_martin",
        "riesgo_pluvial": True,
        "confianza": "alta",
        "motivo": "Cartografia de riesgo a inundaciones y anegamientos (Meza & Ramirez, 2018)",
    },
]


def zonas_con_riesgo_pluvial(confianza_minima: str = "alta"):
    """
    Devuelve la lista de zonas con riesgo pluvial documentado.
    confianza_minima: "alta" (default) filtra solo las respaldadas
    por un estudio tecnico citable.
    """
    if confianza_minima == "alta":
        return [z for z in BARRIOS_RIESGO_PLUVIAL if z["confianza"] == "alta"]
    return BARRIOS_RIESGO_PLUVIAL

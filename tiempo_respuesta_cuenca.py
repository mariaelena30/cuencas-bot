# -*- coding: utf-8 -*-
"""
tiempo_respuesta_cuenca.py
-----------------------------
Portal Hidrico Chaco - Proyecto 2HC26

Estima cuanto tiempo tarda una lluvia caida en el punto mas lejano de
cada cuenca en llegar a la desembocadura (tiempo de concentracion, Tc).
Esto responde a: "si llovio fuerte HOY en la cuenca del Bermejo, cuando
puedo esperar que ese pico de agua llegue"?

BASE ACADEMICA:
Usa los parametros morfometricos oficiales de Gomez (2025), ya cargados
en cuencas_chaco.py: longitud axial (La) y coeficiente de compacidad de
Gravelius (Kc) de cada una de las 4 cuencas del proyecto.

METODO Y LIMITACION IMPORTANTE (leer antes de usar los resultados):
Se usa una forma simplificada del metodo de Kirpich, que requiere
longitud del cauce principal y desnivel/pendiente:

    Tc (horas) = 0.0195 * L^0.77 * S^-0.385 / 60

    donde L = longitud del cauce principal (metros)
          S = pendiente promedio (m/m, adimensional)

El paper de Gomez (2025) da la longitud axial (La) de cada cuenca con
precision, PERO NO da el desnivel/pendiente especifico de cada una -
solo el mapa topografico general de la provincia (altitudes entre
~60 y ~110+ msnm, con pendiente NO-SE). Por eso esta funcion pide la
pendiente como parametro con un valor por defecto ESTIMADO Y AMPLIO,
y devuelve un RANGO (no un numero unico) para no aparentar precision
que no tenemos todavia.

COMO MEJORAR ESTO A FUTURO (pendiente, no bloqueante):
Con QGIS (que ya usas) se puede extraer el perfil de elevacion real a
lo largo del cauce principal de cada cuenca usando el MDE-AR v2.1 (la
misma fuente que uso Gomez), y calcular la pendiente real en vez de
estimarla. Eso reduciria mucho el rango de incertidumbre. Marcado como
tarea pendiente para el proyecto UNNE, no para el hackathon.

Uso:
    from tiempo_respuesta_cuenca import estimar_tiempo_concentracion
    resultado = estimar_tiempo_concentracion("bermejo")
"""

from cuencas_chaco import CUENCAS

# Rango de pendiente estimado para cuencas del Chaco oriental, basado
# en el Mapa 1 del paper de Gomez (altitudes entre 60 y 110+ msnm en un
# territorio de cientos de km de extension NO-SE). Es un rango AMPLIO
# a proposito, para no fingir precision que no existe sin el perfil real.
PENDIENTE_MIN_M_M = 0.00015   # pendiente muy suave (terreno casi plano)
PENDIENTE_MAX_M_M = 0.00060   # pendiente algo mas marcada


def _kirpich_horas(longitud_m: float, pendiente_m_m: float) -> float:
    """Formula de Kirpich (1940), Tc en minutos -> se devuelve en horas."""
    tc_min = 0.0195 * (longitud_m ** 0.77) * (pendiente_m_m ** -0.385)
    return tc_min / 60.0


def estimar_tiempo_concentracion(clave_cuenca: str) -> dict:
    """
    Devuelve un RANGO estimado de horas de respuesta de la cuenca,
    junto con el nivel de confianza del calculo (marcado como bajo,
    porque la pendiente es estimada, no medida).
    """
    cuenca = CUENCAS.get(clave_cuenca)
    if not cuenca:
        return {"error": f"Cuenca '{clave_cuenca}' no reconocida."}

    longitud_m = cuenca["parametros_forma"]["longitud_axial_km"] * 1000
    kc = cuenca["parametros_forma"]["coef_compacidad_gravelius"]

    tc_horas_max_pendiente_min = _kirpich_horas(longitud_m, PENDIENTE_MIN_M_M)  # pendiente suave = Tc mas largo
    tc_horas_min_pendiente_max = _kirpich_horas(longitud_m, PENDIENTE_MAX_M_M)  # pendiente marcada = Tc mas corto

    tc_min = round(min(tc_horas_min_pendiente_max, tc_horas_max_pendiente_min), 1)
    tc_max = round(max(tc_horas_min_pendiente_max, tc_horas_max_pendiente_min), 1)

    # El Kc ya nos dice si la cuenca "achata" o "concentra" la onda de
    # creciente (ver comportamiento_hidrologico en cuencas_chaco.py).
    # Cuencas muy alargadas (Kc alto) tienden al extremo mas largo del
    # rango; se marca como referencia cualitativa, no ajuste numerico.
    tendencia_forma = (
        "hacia el extremo más largo del rango (cuenca alargada, Kc alto)"
        if kc > 2.5 else
        "hacia el centro del rango"
    )

    return {
        "cuenca": cuenca["nombre_oficial"],
        "tc_horas_min": tc_min,
        "tc_horas_max": tc_max,
        "tc_dias_aprox": f"{tc_min/24:.1f} a {tc_max/24:.1f} días",
        "confianza": "baja - pendiente estimada, no medida con MDE real",
        "nota_forma": f"Dada su geometría (Kc={kc}), el tiempo real probablemente se ubique {tendencia_forma}.",
        "mensaje": (
            f"Una lluvia intensa en la parte más alta de esta cuenca podría "
            f"tardar aproximadamente entre {tc_min:.0f} y {tc_max:.0f} horas "
            f"({tc_min/24:.1f} a {tc_max/24:.1f} días) en generar un pico de "
            f"caudal en la desembocadura. Estimación amplia, a mejorar con "
            f"perfil de elevación real en QGIS."
        ),
    }


def estimar_todas() -> dict:
    """Corre la estimacion para las 4 cuencas del proyecto de una vez."""
    return {clave: estimar_tiempo_concentracion(clave) for clave in CUENCAS}


if __name__ == "__main__":
    for clave, resultado in estimar_todas().items():
        print(f"\n=== {clave.upper()} ===")
        for k, v in resultado.items():
            print(f"  {k}: {v}")

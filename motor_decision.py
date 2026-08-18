# -*- coding: utf-8 -*-
"""
motor_decision.py
--------------------
Portal Hidrico Chaco - Proyecto 2HC26

Combina la tendencia de nivel (calcular_tendencia.py) con el estado
actual respecto a los umbrales oficiales para determinar en que FASE
de alerta esta una localidad, y genera el mensaje correspondiente para
cada audiencia. Esta es la pieza que evita dos errores opuestos:
- Informar de mas / generar panico (alertar a todo el mundo por una
  proyeccion incierta a 7 dias).
- Informar de menos / llegar tarde (esperar a que el nivel ya haya
  superado el umbral para avisar, sin haber dado tiempo de reaccion).

LAS 4 FASES (ver tabla completa en el documento del proyecto):

  MONITOREO   -> disparada por proyeccion lejana (>72hs) o dato de
                 referencia (represa vertio, lluvia fuerte aguas arriba).
                 Audiencia: SOLO panel tecnico / Defensa Civil.
                 No se muestra al vecino - evita alarmar por algo que
                 todavia puede no pasar.

  ATENCION    -> proyeccion de tocar el umbral de alerta en <72 horas,
                 con tendencia confiable (ver calcular_tendencia.py).
                 Audiencia: Defensa Civil + bomberos de la localidad.
                 Tiempo de empezar a preparar (revisar refugios, listas).

  ALERTA      -> el nivel REAL ya supero el umbral de alerta oficial
                 (Prefectura Naval Argentina, no el de CIMA que es poco
                 confiable para evacuacion, ver dashboard_simple.py).
                 Audiencia: vecinos de la localidad + Defensa Civil.

  EVACUACION  -> el nivel REAL ya supero el umbral de evacuacion oficial.
                 Audiencia: todos, con foco en barrios vulnerables
                 especificos ya identificados (BARRIOS_VULNERABLES).

NOTA: este motor consume los umbrales OFICIALES de Prefectura (los que
ya cargaste en tu backend/main.py), no los del API de CIMA.
"""

from calcular_tendencia import calcular_tendencia, proyectar_umbral


def determinar_fase(altura_actual: float, umbral_alerta: float, umbral_evacuacion: float,
                     lecturas_historicas: list[dict] = None) -> dict:
    """
    Determina la fase actual de una localidad.

    lecturas_historicas: lista de {"fecha": ISO8601, "altura": float}
        Si no se pasa (o hay muy pocas), el motor solo puede evaluar el
        estado ACTUAL (Alerta/Evacuacion/Normal) sin proyeccion futura
        (no puede detectar fase Atencion/Monitoreo con anticipacion).
    """
    if altura_actual is None:
        return _fase_sin_dato()

    # --- Paso 1: estado segun nivel REAL (esto manda siempre) ---
    if altura_actual >= umbral_evacuacion:
        return _fase_evacuacion(altura_actual, umbral_evacuacion)

    if altura_actual >= umbral_alerta:
        return _fase_alerta(altura_actual, umbral_alerta, umbral_evacuacion)

    # --- Paso 2: si el nivel real todavia es normal, miramos la
    #     PROYECCION para ver si conviene pasar a Atencion o Monitoreo ---
    if lecturas_historicas and len(lecturas_historicas) >= 2:
        tendencia = calcular_tendencia(lecturas_historicas)
        proyeccion = proyectar_umbral(tendencia, umbral_alerta)

        if proyeccion and proyeccion.get("estado") == "proyectado":
            dias = proyeccion["dias_estimados"]
            if dias is not None and dias <= 3 and proyeccion.get("confiable"):
                return _fase_atencion(altura_actual, proyeccion, tendencia)
            if dias is not None and dias <= 7:
                return _fase_monitoreo(altura_actual, proyeccion, tendencia)

    return _fase_normal(altura_actual)


# --- Constructores de cada fase, con mensaje ya redactado por audiencia ---

def _fase_normal(altura):
    return {
        "fase": "NORMAL",
        "color": "verde",
        "mostrar_a_vecinos": True,
        "mensaje_vecino": "El río está en su nivel normal. No hay riesgo por ahora.",
        "mensaje_tecnico": f"Nivel actual {altura:.2f} m, dentro de rango normal. Sin acción requerida.",
    }


def _fase_monitoreo(altura, proyeccion, tendencia):
    return {
        "fase": "MONITOREO",
        "color": "gris_tecnico",
        "mostrar_a_vecinos": False,  # a proposito: no se muestra al publico
        "mensaje_vecino": None,
        "mensaje_tecnico": (
            f"[SOLO PERSONAL] Nivel actual {altura:.2f} m. {tendencia['mensaje']} "
            f"{proyeccion['mensaje']} Sin acción pública todavía - registrar y "
            f"seguir de cerca la próxima lectura."
        ),
    }


def _fase_atencion(altura, proyeccion, tendencia):
    return {
        "fase": "ATENCION",
        "color": "amarillo",
        "mostrar_a_vecinos": True,
        "mensaje_vecino": (
            "El río está subiendo. Todavía no hay riesgo, pero es un buen "
            "momento para revisar lo esencial (documentos, medicamentos) y "
            "estar atento a los próximos avisos."
        ),
        "mensaje_tecnico": (
            f"[DEFENSA CIVIL / BOMBEROS] Nivel {altura:.2f} m. {tendencia['mensaje']} "
            f"{proyeccion['mensaje']} Recomendado: iniciar preparativos "
            f"(revisión de refugios, contacto con barrios vulnerables)."
        ),
    }


def _fase_alerta(altura, umbral_alerta, umbral_evacuacion):
    return {
        "fase": "ALERTA",
        "color": "naranja",
        "mostrar_a_vecinos": True,
        "mensaje_vecino": (
            f"⚠️ El río superó el nivel de alerta ({umbral_alerta} m). "
            f"Prestá atención a los avisos de Defensa Civil de tu localidad "
            f"y tené preparado lo esencial para vos y tus mascotas."
        ),
        "mensaje_tecnico": (
            f"[ALERTA ACTIVA] Nivel {altura:.2f} m, superó umbral de alerta "
            f"({umbral_alerta} m). Falta {umbral_evacuacion - altura:.2f} m "
            f"para umbral de evacuación."
        ),
    }


def _fase_evacuacion(altura, umbral_evacuacion):
    return {
        "fase": "EVACUACION",
        "color": "rojo",
        "mostrar_a_vecinos": True,
        "mensaje_vecino": (
            f"🔴 El río superó el nivel de evacuación ({umbral_evacuacion} m). "
            f"Seguí las indicaciones de Defensa Civil y Bomberos de tu zona. "
            f"Priorizá tu seguridad y la de tu familia y mascotas."
        ),
        "mensaje_tecnico": (
            f"[EVACUACIÓN ACTIVA] Nivel {altura:.2f} m, superó umbral de "
            f"evacuación ({umbral_evacuacion} m). Activar protocolo con "
            f"barrios vulnerables identificados de la localidad."
        ),
    }


def _fase_sin_dato():
    return {
        "fase": "SIN_DATO",
        "color": "gris",
        "mostrar_a_vecinos": True,
        "mensaje_vecino": "No pudimos obtener el dato en este momento. Probá de nuevo en unos minutos.",
        "mensaje_tecnico": "Sin datos disponibles de esta estación.",
    }


if __name__ == "__main__":
    # Ejemplo: localidad con nivel normal pero subiendo rapido -> deberia
    # dar ATENCION, no NORMAL ni ALERTA todavia
    historico_ejemplo = [
        {"fecha": "2026-08-14T08:00:00", "altura": 4.80},
        {"fecha": "2026-08-15T08:00:00", "altura": 5.10},
        {"fecha": "2026-08-16T08:00:00", "altura": 5.45},
        {"fecha": "2026-08-17T08:00:00", "altura": 5.75},
    ]
    resultado = determinar_fase(
        altura_actual=5.75,
        umbral_alerta=6.00,
        umbral_evacuacion=6.50,
        lecturas_historicas=historico_ejemplo,
    )
    print("Fase:", resultado["fase"])
    print("Mostrar a vecinos:", resultado["mostrar_a_vecinos"])
    print("Mensaje vecino:", resultado["mensaje_vecino"])
    print("Mensaje técnico:", resultado["mensaje_tecnico"])

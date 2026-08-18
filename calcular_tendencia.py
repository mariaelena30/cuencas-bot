# -*- coding: utf-8 -*-
"""
calcular_tendencia.py
------------------------
Portal Hidrico Chaco - Proyecto 2HC26

Convierte una serie de lecturas de nivel (las que ya guarda el pipeline
via obtener_niveles_rios.py) en una PROYECCION: a este ritmo, cuantas
horas/dias faltan para tocar el umbral de alerta o de evacuacion.

Esto es lo que transforma el dashboard de "foto del momento" a
"herramienta de anticipacion". Un nivel de 3.02 m no dice nada por si
solo; "subiendo 8 cm por dia, va a tocar alerta en 4 dias" si permite
actuar antes de que sea tarde.

IMPORTANTE - limitaciones honestas de este calculo:
- Es una PROYECCION LINEAL simple (regresion sobre los ultimos N puntos).
  Los rios no suben de forma lineal: pueden acelerar (nueva lluvia aguas
  arriba, apertura de compuertas) o frenar (bajante natural). Esta
  funcion NO reemplaza un modelo hidrologico calibrado, es un primer
  indicador de tendencia para priorizar donde mirar con mas atencion.
- Necesita al menos 3 lecturas espaciadas en el tiempo para ser
  confiable. Con 2 puntos (altura actual vs anterior) la proyeccion es
  muy ruidosa - lo ideal es ir guardando el historico dia a dia
  (agregar cada corrida del pipeline a un archivo historico_niveles.csv
  en vez de sobrescribirlo) para tener una serie real.
- Cuanto mas lejos se proyecta en el tiempo, menos confiable es. Por
  eso se marca la proyeccion como "referencial" mas alla de 5-7 dias.

Uso tipico (una vez que tengas el historico acumulado):
    from calcular_tendencia import calcular_tendencia, proyectar_umbral

    lecturas = [
        {"fecha": "2026-08-15T08:00:00", "altura": 2.95},
        {"fecha": "2026-08-16T08:00:00", "altura": 3.02},
        {"fecha": "2026-08-17T08:00:00", "altura": 3.11},
    ]
    tendencia = calcular_tendencia(lecturas)
    proyeccion = proyectar_umbral(tendencia, umbral_alerta=6.00)
"""

from datetime import datetime, timedelta
from typing import Optional


def _parsear_fecha(fecha_str: str) -> datetime:
    """Acepta ISO 8601 con o sin timezone."""
    try:
        return datetime.fromisoformat(fecha_str.replace("Z", "+00:00"))
    except ValueError:
        # Fallback simple para formatos tipo "2026-08-17 08:00:00"
        return datetime.strptime(fecha_str[:19], "%Y-%m-%d %H:%M:%S")


def calcular_tendencia(lecturas: list[dict]) -> dict:
    """
    Recibe una lista de lecturas ordenadas cronologicamente:
        [{"fecha": "ISO8601", "altura": float(metros)}, ...]

    Devuelve la tasa de cambio (m/dia) mediante regresion lineal simple
    sobre los puntos disponibles, junto con metadata de confiabilidad.
    """
    lecturas_validas = [
        l for l in lecturas
        if l.get("altura") is not None and l.get("fecha")
    ]

    if len(lecturas_validas) < 2:
        return {
            "tasa_m_por_dia": None,
            "confiabilidad": "insuficiente",
            "n_lecturas": len(lecturas_validas),
            "mensaje": "Se necesitan al menos 2 lecturas para calcular tendencia.",
        }

    # Convertir fechas a "dias transcurridos desde la primera lectura"
    fechas = [_parsear_fecha(l["fecha"]) for l in lecturas_validas]
    t0 = fechas[0]
    x = [(f - t0).total_seconds() / 86400.0 for f in fechas]  # dias (float)
    y = [l["altura"] for l in lecturas_validas]

    n = len(x)
    if n == 2:
        # Con solo 2 puntos, la "regresion" es simplemente la pendiente
        # entre ambos - funciona pero es poco confiable.
        dx = x[1] - x[0]
        tasa = (y[1] - y[0]) / dx if dx > 0 else 0.0
        confiabilidad = "baja"
    else:
        # Regresion lineal simple (minimos cuadrados) con las lecturas
        # disponibles - mas puntos, mejor estimacion de la tendencia real.
        x_prom = sum(x) / n
        y_prom = sum(y) / n
        num = sum((x[i] - x_prom) * (y[i] - y_prom) for i in range(n))
        den = sum((x[i] - x_prom) ** 2 for i in range(n))
        tasa = num / den if den != 0 else 0.0
        confiabilidad = "media" if n < 5 else "aceptable"

    altura_actual = y[-1]

    return {
        "tasa_m_por_dia": round(tasa, 4),
        "tasa_cm_por_dia": round(tasa * 100, 1),
        "altura_actual": altura_actual,
        "confiabilidad": confiabilidad,
        "n_lecturas": n,
        "periodo_dias": round(x[-1] - x[0], 2),
        "mensaje": _mensaje_tendencia(tasa),
    }


def _mensaje_tendencia(tasa_m_dia: float) -> str:
    cm_dia = tasa_m_dia * 100
    if abs(cm_dia) < 1:
        return "Nivel estable."
    direccion = "subiendo" if cm_dia > 0 else "bajando"
    return f"Nivel {direccion} a razón de aproximadamente {abs(cm_dia):.1f} cm por día."


def proyectar_umbral(tendencia: dict, umbral_metros: float) -> Optional[dict]:
    """
    Dado el resultado de calcular_tendencia() y un umbral (alerta o
    evacuacion, en metros), estima en cuantos dias se alcanzaria ese
    umbral SI la tendencia actual se mantiene constante (supuesto que
    hay que comunicar siempre junto con el resultado).

    Devuelve None si el nivel esta bajando o estable (no hay proyeccion
    de alcanzar el umbral) o si no hay tendencia confiable.
    """
    tasa = tendencia.get("tasa_m_por_dia")
    altura_actual = tendencia.get("altura_actual")

    if tasa is None or altura_actual is None:
        return None

    if altura_actual >= umbral_metros:
        return {
            "dias_estimados": 0,
            "estado": "ya_superado",
            "mensaje": "El nivel ya superó este umbral.",
        }

    if tasa <= 0:
        return {
            "dias_estimados": None,
            "estado": "sin_riesgo_inmediato",
            "mensaje": "El nivel no está subiendo, no se proyecta alcanzar este umbral en el corto plazo.",
        }

    dias = (umbral_metros - altura_actual) / tasa
    confiable = dias <= 7 and tendencia.get("confiabilidad") in ("media", "aceptable")

    return {
        "dias_estimados": round(dias, 1),
        "fecha_estimada": (datetime.now() + timedelta(days=dias)).strftime("%d/%m/%Y"),
        "estado": "proyectado",
        "confiable": confiable,
        "mensaje": (
            f"A este ritmo, se estima alcanzar los {umbral_metros} m en unos "
            f"{dias:.1f} días (aprox. {(datetime.now() + timedelta(days=dias)).strftime('%d/%m')})."
            + ("" if confiable else " Proyección poco confiable por horizonte largo o pocos datos - tomar como orientativa, no como pronóstico.")
        ),
    }


if __name__ == "__main__":
    # Ejemplo de prueba con una serie simulada de ascenso sostenido
    lecturas_ejemplo = [
        {"fecha": "2026-08-14T08:00:00", "altura": 2.80},
        {"fecha": "2026-08-15T08:00:00", "altura": 2.95},
        {"fecha": "2026-08-16T08:00:00", "altura": 3.05},
        {"fecha": "2026-08-17T08:00:00", "altura": 3.18},
    ]
    tendencia = calcular_tendencia(lecturas_ejemplo)
    print("Tendencia:", tendencia)
    proyeccion_alerta = proyectar_umbral(tendencia, umbral_metros=6.00)
    print("Proyección a umbral de alerta (6.00 m):", proyeccion_alerta)

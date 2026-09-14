"""
Generador de alertas hidrometeorológicas, con el mismo formato y lógica
de clasificación de severidad que usan las fuentes oficiales (SMN
Argentina, SEN Paraguay, INA) en sus propias alertas.

Los umbrales de severidad de abajo NO son un valor único publicado por
el SMN en una tabla oficial — el SMN no publica esos números en un
documento fijo — sino un patrón extraído de decenas de alertas reales
emitidas por el organismo a lo largo de 2026, que se repite de forma
consistente:

  AMARILLA: acumulados de lluvia ~20-60 mm, ráfagas hasta ~60-80 km/h,
            actividad eléctrica y granizo ocasional. "Capacidad de daño,
            riesgo de interrupción momentánea de actividades cotidianas."
  NARANJA:  acumulados de lluvia ~60-100 mm, ráfagas de ~80-100+ km/h,
            actividad eléctrica frecuente y granizo. "Peligrosos para la
            sociedad, la vida, los bienes y el medio ambiente."
  ROJA:     por encima de esos valores (poco frecuente, se reserva para
            eventos extremos) — acá se clasifica como tal si se superan
            ampliamente los umbrales de naranja.

Esto es un generador propio, complementario — NO reemplaza ni debe
presentarse como una alerta oficial del SMN/INA/SEN. Cada alerta generada
debe indicar de dónde salen los datos crudos (ej. Open-Meteo, estación
propia) para que quede claro que es un análisis propio basado en esas
fuentes, no una alerta emitida por ellas.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import List, Optional
from enum import Enum


class NivelSeveridad(str, Enum):
    SIN_ALERTA = "SIN_ALERTA"
    AMARILLA = "AMARILLA"
    NARANJA = "NARANJA"
    ROJA = "ROJA"


@dataclass
class AlertaHidrometeorologica:
    titulo: str
    nivel: NivelSeveridad
    periodo_desde: datetime
    periodo_hasta: datetime
    detalle: List[str]  # bullets: lluvia, viento, tormenta eléctrica, granizo
    area: str
    fuente_datos: str  # de dónde salen los datos crudos usados (Open-Meteo, estación propia, etc.)
    emitido_por: str  # quién generó ESTA alerta (para dejar claro que no es el SMN)
    timestamp_emision: datetime

    def to_texto(self) -> str:
        """Formato de salida similar al de las apps oficiales (SEN/SMN)."""
        lineas = [
            f"{self.titulo} — Nivel {self.nivel.value}",
            f"de: {self.periodo_desde.strftime('%d/%m/%Y, %H:%M')}",
            f"a: {self.periodo_hasta.strftime('%d/%m/%Y, %H:%M')}",
            "",
        ]
        lineas += [f"• {item}" for item in self.detalle]
        lineas += [
            "",
            f"Área: {self.area}",
            f"Datos crudos: {self.fuente_datos} — esta alerta es un análisis propio, no un aviso oficial.",
            f"Generado por: {self.emitido_por}",
            f"Emitido: {self.timestamp_emision.strftime('%d/%m/%Y, %H:%M')}",
        ]
        return "\n".join(lineas)


def clasificar_severidad(precipitacion_mm: float, rafagas_kmh: float) -> NivelSeveridad:
    """
    Clasifica el nivel de severidad combinando lluvia acumulada prevista
    y ráfagas de viento, siguiendo el patrón real de alertas del SMN
    (ver docstring del módulo).
    """
    if precipitacion_mm >= 100 or rafagas_kmh >= 100:
        return NivelSeveridad.ROJA
    if precipitacion_mm >= 60 or rafagas_kmh >= 80:
        return NivelSeveridad.NARANJA
    if precipitacion_mm >= 20 or rafagas_kmh >= 60:
        return NivelSeveridad.AMARILLA
    return NivelSeveridad.SIN_ALERTA


def generar_alerta_tormenta(
    area: str,
    precipitacion_mm_prevista: float,
    rafagas_kmh_previstas: float,
    horas_vigencia: int = 24,
    hay_actividad_electrica: bool = True,
    hay_granizo_posible: bool = False,
    fuente_datos: str = "Open-Meteo (modelo)",
    emitido_por: str = "Portal Hídrico Chaco — generador propio",
    ahora: Optional[datetime] = None,
) -> Optional[AlertaHidrometeorologica]:
    """
    Genera una alerta con el mismo formato que usan las apps oficiales,
    a partir de los datos ya procesados por tu propio pipeline (por
    ejemplo, la salida de analisis_meteorologico.py + un pronóstico de
    lluvia/viento de Open-Meteo). Devuelve None si no se alcanza ningún
    umbral de severidad (no hay alerta que emitir).
    """
    nivel = clasificar_severidad(precipitacion_mm_prevista, rafagas_kmh_previstas)
    if nivel == NivelSeveridad.SIN_ALERTA:
        return None

    ahora = ahora or datetime.now()

    detalle = [
        f"Lluvias: acumulados de entre {precipitacion_mm_prevista * 0.7:.0f} y "
        f"{precipitacion_mm_prevista:.0f} mm y puntualmente superiores.",
        f"Vientos: ráfagas en torno a los {rafagas_kmh_previstas:.0f} km/h y puntualmente superiores.",
    ]
    if hay_actividad_electrica:
        detalle.append("Tormentas eléctricas: con alta frecuencia sobre el área.")
    if hay_granizo_posible:
        detalle.append("Granizo: ocasional caída en forma puntual.")

    return AlertaHidrometeorologica(
        titulo="Sistemas de tormentas",
        nivel=nivel,
        periodo_desde=ahora,
        periodo_hasta=ahora + timedelta(hours=horas_vigencia),
        detalle=detalle,
        area=area,
        fuente_datos=fuente_datos,
        emitido_por=emitido_por,
        timestamp_emision=ahora,
    )


if __name__ == "__main__":
    alerta = generar_alerta_tormenta(
        area="Barranqueras y Puerto Vilelas — Severa",
        precipitacion_mm_prevista=90,
        rafagas_kmh_previstas=100,
        hay_granizo_posible=True,
    )
    if alerta:
        print(alerta.to_texto())
    else:
        print("Sin alerta: no se alcanzó ningún umbral de severidad.")

# -*- coding: utf-8 -*-
"""
cuencas_chaco.py
------------------
Portal Hidrico Chaco - Proyecto 2HC26

Fuente canonica de la definicion de las 4 cuencas que monitorea el
proyecto (Bermejo, Rio de Oro, Tragadero, Negro-Salado).

Todos los datos morfometricos, colectores principales, afluentes y
coordenadas de referencia estan tomados directamente de:

    Gomez, C. V. (2025). Delimitacion y caracterizacion morfometrica de
    las cuencas hidrograficas de la provincia del Chaco, Argentina.
    Cuadernos Docentes N 11. Instituto de Investigaciones Geohistoricas,
    CONICET - Universidad Nacional del Nordeste. ISSN 0326-2766.

Metodologia de la fuente: MDE-AR v2.1 (IGN) procesados con ArcHydro
(ArcGIS 10.8), validados contra imagenes Landsat 8-9. Este documento es
la propuesta academica mas reciente y detallada disponible para las
cuencas del Chaco (reemplaza en precision, aunque no en uso oficial
vigente, a la Resolucion 711/06 de Administracion Provincial del Agua).

Por que importan los parametros de forma (Kc, Kf, Rc) para el proyecto:
una cuenca compacta/redondeada concentra el agua de lluvia mas rapido
en un pico de creciente alto y breve (mas peligroso, menos tiempo de
reaccion). Una cuenca alargada modera y "achata" la onda de creciente,
dando mas tiempo de alerta pero con crecidas mas sostenidas en el
tiempo. Este dato se usa en generar_mensaje_simple() para dar contexto
en lenguaje llano sin exponer los numeros crudos al usuario final.
"""

CUENCAS = {
    "bermejo": {
        "nombre_oficial": "Cuenca del rio Bermejo",
        "colector_principal": "Rio Bermejo",
        "afluentes": ["Rio Teuco", "Rio La Union", "Riacho Salado", "Rio Bermejito"],
        "desemboca_en": "Rio Parana (directo)",
        "tipo": "exorreica",
        "departamentos": ["General Guemes", "Libertador Gral. San Martin", "Bermejo"],
        "bbox_aprox": {  # 24-27 S, 58.5-62.5 O (incluye tramo en Formosa, impreciso ahi)
            "lat_min": -27.0, "lat_max": -24.0,
            "lon_min": -62.5, "lon_max": -58.5,
        },
        "parametros_forma": {
            "area_km2": 14492.00,
            "perimetro_km": 1272.00,
            "longitud_axial_km": 491.00,
            "ancho_promedio_km": 29.50,
            "coef_compacidad_gravelius": 2.98,   # >1.75 = casi rectangular, alargada
            "factor_forma_horton": 0.06,          # <0.22 = muy alargada
            "radio_circularidad_miller": 0.11,    # 0-0.25 = oblonga, bajo potencial de crecientes
        },
        "clasificacion_tamano": "mediano",
        "comportamiento_hidrologico": (
            "Cuenca muy alargada y de forma oblonga. Segun su geometria, "
            "modera la onda de creciente (la achata): las crecidas tienden "
            "a ser mas sostenidas en el tiempo pero con picos menos "
            "subitos que en una cuenca compacta. Sin embargo, al no tener "
            "grandes represas de regulacion aguas arriba (a diferencia del "
            "Parana), sus crecidas por lluvia intensa localizada pueden ser "
            "rapidas igualmente."
        ),
    },
    "oro": {
        "nombre_oficial": "Cuenca del rio Oro",
        "colector_principal": "Rio de Oro (colector de orden 2)",
        "afluentes": ["Arroyo Cangui Chico", "Arroyo Cangui Grande", "Arroyo Zapiran",
                       "Arroyo Correntoso", "Canada La Mala"],
        "desemboca_en": "Rio Parana (directo, sin intermediarios)",
        "tipo": "exorreica",
        "departamentos": ["Libertador Gral. San Martin", "Bermejo"],
        "bbox_aprox": {  # 25.83-27 S, 58.5-60.17 O
            "lat_min": -27.0, "lat_max": -25.83,
            "lon_min": -60.17, "lon_max": -58.5,
        },
        "parametros_forma": {
            "area_km2": 4602.00,
            "perimetro_km": 554.00,
            "longitud_axial_km": 216.00,
            "ancho_promedio_km": 21.30,
            "coef_compacidad_gravelius": 2.30,
            "factor_forma_horton": 0.10,
            "radio_circularidad_miller": 0.19,
        },
        "clasificacion_tamano": "pequeño",
        "comportamiento_hidrologico": (
            "Cuenca alargada, de las mas pequeñas del sistema. Modera "
            "moderadamente la onda de creciente. Es la que pasa por "
            "General Vedia."
        ),
    },
    "tragadero": {
        "nombre_oficial": "Cuenca del rio Tragadero",
        "colector_principal": "Rio Tragadero",
        "afluentes": ["Arroyo El Embalsadito", "Arroyo Caroli", "Arroyo Quintana",
                       "Arroyo Tragadero-Embalsado"],
        "desemboca_en": "Rio Barranqueras, y este al Rio Parana",
        "tipo": "exorreica",
        "departamentos": ["Sargento Cabral", "General Donovan", "Libertad",
                            "1 de Mayo", "San Fernando"],
        "bbox_aprox": {  # 26.67-27.42 S, 58.83-59.67 O
            "lat_min": -27.42, "lat_max": -26.67,
            "lon_min": -59.67, "lon_max": -58.83,
        },
        "parametros_forma": {
            "area_km2": 1104.00,
            "perimetro_km": 319.00,
            "longitud_axial_km": 88.00,
            "ancho_promedio_km": 12.50,
            "coef_compacidad_gravelius": 2.71,
            "factor_forma_horton": 0.14,
            "radio_circularidad_miller": 0.14,
        },
        "clasificacion_tamano": "pequeño",
        "comportamiento_hidrologico": (
            "Cuenca chica y alargada. Organiza el drenaje de Colonia "
            "Benitez y descarga directamente hacia el Rio Barranqueras, "
            "que es el mismo curso que recibe al sistema Negro-Salado. "
            "Por eso el nivel del Parana en Barranqueras es un buen proxy "
            "de referencia para esta cuenca: si el Parana esta alto, el "
            "Tragadero no puede drenar bien aunque no este lloviendo "
            "localmente."
        ),
    },
    "negro_salado": {
        "nombre_oficial": "Cuenca de los rios Negro-Salado",
        "colector_principal": "Rio Negro y Rio Salado (conectados por canal artificial)",
        "afluentes": ["Riacho Nogueira", "Zanjon del Rio Negro", "Zanjon Salto La Vieja",
                       "Riacho Salto La Vieja", "Estero Saladillo", "Arroyo Saladillo",
                       "Arroyo El Chancho"],
        "desemboca_en": "Rio Negro -> Rio Barranqueras -> Parana | "
                          "Rio Salado -> Rio Paranacito -> Parana",
        "tipo": "exorreica",
        "departamentos": ["General Guemes", "Maipu", "25 de Mayo", "Quitilipi",
                            "Comandante Fernandez", "Presidencia de la Plaza",
                            "General Donovan", "Sargento Cabral", "Libertad",
                            "San Fernando"],
        "bbox_aprox": {  # 26-27.75 S, 58.83-60.5 O
            "lat_min": -27.75, "lat_max": -26.0,
            "lon_min": -60.5, "lon_max": -58.83,
        },
        "parametros_forma": {
            "area_km2": 10154.00,
            "perimetro_km": 743.00,
            "longitud_axial_km": 183.00,
            "ancho_promedio_km": 55.50,
            "coef_compacidad_gravelius": 2.08,
            "factor_forma_horton": 0.30,   # la mas "ensanchada" de las 4
            "radio_circularidad_miller": 0.23,
        },
        "clasificacion_tamano": "mediano",
        "comportamiento_hidrologico": (
            "La mas grande y mas ensanchada de las 4 cuencas del proyecto "
            "(factor de forma mas alto = tiende un poco mas hacia formas "
            "que concentran la escorrentia que las otras tres). El Rio "
            "Negro y el Rio Salado estan unidos por un canal artificial "
            "que deriva agua del primero al segundo en momentos de "
            "creciente, asi que ambos se comportan como un sistema unico "
            "en eventos extremos aunque el resto del tiempo tengan "
            "dinamicas distintas. Atraviesa gran parte del area central "
            "de la provincia, por lo que concentra el drenaje de muchos "
            "departamentos."
        ),
    },
}


def generar_mensaje_simple(clave_cuenca: str) -> str:
    """
    Devuelve una descripcion en lenguaje llano del comportamiento de la
    cuenca, pensada para mostrar al usuario final (Capa 2 del esquema de
    3 capas: semaforo -> frase simple -> dato tecnico completo).
    """
    c = CUENCAS.get(clave_cuenca)
    if not c:
        return "Cuenca no reconocida."
    return (
        f"{c['nombre_oficial']}: colector principal {c['colector_principal']}, "
        f"desemboca en {c['desemboca_en']}. {c['comportamiento_hidrologico']}"
    )


if __name__ == "__main__":
    # Prueba rapida: imprime resumen de las 4 cuencas
    for clave in CUENCAS:
        print(f"\n=== {clave.upper()} ===")
        print(generar_mensaje_simple(clave))

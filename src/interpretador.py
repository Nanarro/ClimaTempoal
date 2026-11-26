"""
Interpretador de datos para el texto del reporte diario.

Convierte los números del pronóstico en frases claras, decisivas y
amigables: el lector no debe tener que interpretar datos sueltos.
La tarjeta diaria NO cambia (sigue con todos sus datos); esto es
solo para el texto del reporte.

Reglas aprobadas por el usuario (2026-11-26):
- Viento: si es flojo y no cambia nada, no aparece. Si importa, se
  dice qué causa (sensación térmica, lluvia arrastrada, riesgo de
  ramas, etc.).
- Presión: si está normal y estable, no aparece. Si baja o sube
  fuerte, se dice qué anuncia.
- Temperatura: sensación primero ("hará frío, unos 15 °C"); mín/máx
  solo cuando el rango importa.
- Lluvia: palabras decisivas según la probabilidad real del ensemble,
  y además la probabilidad de lluvia FUERTE (segunda probabilidad
  del ensemble) cuando aplica.

REGLA DURA para comparaciones especiales: nunca inventar eventos,
fechas ni récords históricos. Las únicas comparaciones permitidas
son (a) contra la ventana de 7 días del propio pronóstico
("el día más lluvioso de la semana") y (b) referencias genéricas
locales sin fecha ("como un norte fuerte"). Si una comparación
necesitaría un dato que el bot no tiene, no se hace.

Todas las funciones son puras: reciben dicts con los datos y
devuelven texto (o None cuando no hay nada que decir). Así se
pueden probar sin red ni Telegram.
"""

# ---------------------------------------------------------------------------
# Umbrales (todos documentados: por qué ese valor)
# ---------------------------------------------------------------------------

# Viento (km/h). Escala Beaufort aproximada: <10 es brisa ligera
# (hojas que apenas se mueven, no cambia la sensación ni la lluvia);
# 20 es brisa moderada (se siente, mueve ramas pequeñas); 40 es
# viento fuerte (Protección Civil: puede tumbar ramas y objetos).
VIENTO_MINIMO_RELEVANTE_KMH = 10.0
VIENTO_MODERADO_KMH = 20.0
VIENTO_FUERTE_KMH = 40.0
# Ráfaga que ya merece mencionarse aunque el viento medio sea menor.
RAFAGA_FUERTE_KMH = 40.0

# Presión (hPa). La presión normal al nivel del mar ronda 1013 hPa y
# en la costa del Golfo moverse entre 1005 y 1025 es rutina. Fuera
# de esa banda, o con un cambio de 3 hPa o más en el día (la
# variación normal diaria es de 1-2 hPa), ya anuncia algo.
PRESION_NORMAL_MIN_HPA = 1005.0
PRESION_NORMAL_MAX_HPA = 1025.0
PRESION_CAMBIO_HPA = 3.0

# Lluvia fuerte: acumulado por bloque (6 h) de 10 mm o más. Es el
# mismo umbral que etiqueta_bloque usa para "LLUVIAS FUERTES".
UMBRAL_LLUVIA_FUERTE_MM = 10.0

# Temperatura: la sensación (aparente) manda sobre la media, porque
# es lo que el cuerpo siente. Si sensación y media difieren 3 °C o
# más, vale la pena decirlo ("se sentirá de 12 °C").
DIFERENCIA_SENSACION_C = 3.0
# Rango mín-máx dentro de un bloque que ya importa contarlo
# (una mañana que empieza fría y termina templada, por ejemplo).
RANGO_TEMP_RELEVANTE_C = 5.0

# Comparación especial: umbrales que marcan un día fuera de lo común
# para Tempoal. Solo entonces se permite una frase de referencia.
ESPECIAL_LLUVIA_BLOQUES = 90      # lluvia >= 90% en los 3 bloques
ESPECIAL_VIENTO_KMH = 50          # viento máximo del día
ESPECIAL_TEMP_MAX_FRIO_C = 18     # máxima del día (día muy frío)
ESPECIAL_TEMP_MIN_FRIO_C = 10     # mínima del día (mañana muy fría)
ESPECIAL_LLUVIA_DIA_MM = 30       # lluvia acumulada del día
ESPECIAL_CAIDA_PRESION_HPA = 5    # caída de presión en el día

# Nombre del bloque para usar dentro de una frase ("lluvia en la
# mañana", "lluvia de la tarde"). El nombre visible es "POR LA
# MAÑANA" (para no confundirlo con "mañana" = el día siguiente),
# pero dentro de una frase se usa "mañana" ("en la mañana").
NOMBRE_FRASE = {
    'POR LA MAÑANA': 'mañana',
    'TARDE': 'tarde',
    'NOCHE': 'noche',
}


def _nombre_frase(bloque):
    """Nombre del bloque para usar dentro de una frase."""
    nombre = (bloque.get('nombre') or '').upper()
    return NOMBRE_FRASE.get(nombre, nombre.lower())


def _num(valor, decimales=0):
    """Número redondeado (entero si decimales=0), o None si no hay valor."""
    if valor is None:
        return None
    if decimales == 0:
        return int(round(float(valor)))
    return round(float(valor), decimales)


# ---------------------------------------------------------------------------
# Lluvia (con las dos probabilidades del ensemble)
# ---------------------------------------------------------------------------

def frase_lluvia(bloque):
    """
    Frase decisiva sobre la lluvia de un bloque.

    Usa la probabilidad real del ensemble (prob_max ya es la del
    ensemble cuando hay datos; si no, la determinista) y, cuando
    existe, la probabilidad de lluvia FUERTE (prob_lluvia_fuerte_ens:
    % de miembros con más de 10 mm acumulados en el bloque). Esa
    segunda probabilidad es lo que distingue "lloverá seguro pero
    ligero" de "lloverá seguro y fuerte".
    """
    prob = _num(bloque.get('prob_max')) or 0
    fuerte = bloque.get('prob_lluvia_fuerte_ens')
    mm = bloque.get('lluvia_mm') or 0

    if prob >= 90:
        frase = f"lluvia casi segura ({prob}%)"
    elif prob >= 70:
        frase = f"lluvia muy probable ({prob}%)"
    elif prob >= 50:
        frase = f"probable que llueva ({prob}%)"
    elif prob >= 30:
        return f"alguna llovizna o lluvia ligera de vez en cuando ({prob}%)"
    elif prob >= 15:
        return f"puede caer alguna llovizna ({prob}%)"
    else:
        return "sin lluvia esperada"

    # Solo si lloverá de verdad importa si será fuerte o ligera.
    if prob >= 50:
        if fuerte is not None:
            if fuerte >= 50:
                frase += ", puede llover fuerte por ratos"
            elif fuerte >= 25:
                frase += ", con algunos chubascos fuertes"
            elif prob >= 70:
                frase += ", pero ligera"
        elif mm >= UMBRAL_LLUVIA_FUERTE_MM:
            # Sin ensemble: el acumulado determinista es lo que hay.
            frase += ", puede llover fuerte por ratos"
        elif mm >= 5:
            frase += ", con chubascos"
    return frase


# ---------------------------------------------------------------------------
# Viento (solo aparece si causa algo)
# ---------------------------------------------------------------------------

def frase_viento(bloque):
    """
    Frase sobre el viento de un bloque, o None si no hay nada que
    decir: un viento flojo (menos de 10 km/h) no cambia la sensación
    ni la lluvia, así que no se menciona. Cuando importa, se dice
    qué causa, no solo su velocidad.
    """
    vmax = bloque.get('viento_max')
    if vmax is None or vmax < VIENTO_MINIMO_RELEVANTE_KMH:
        return None
    direccion = bloque.get('viento_dir')
    dir_txt = f" del {direccion.lower()}" if direccion else ""
    prob = _num(bloque.get('prob_max')) or 0
    media = bloque.get('temp_media')
    rafaga = bloque.get('rafaga_max')

    if vmax >= VIENTO_FUERTE_KMH:
        if media is not None and media <= 20:
            frase = (f"viento fuerte{dir_txt}: se sentirá más frío "
                     "y puede tumbar ramas")
        else:
            frase = (f"viento fuerte{dir_txt} que puede tumbar ramas "
                     "y objetos sueltos")
    elif vmax >= VIENTO_MODERADO_KMH:
        if prob >= 60:
            frase = f"viento moderado{dir_txt} que empujará la lluvia"
        elif media is not None and media <= 18:
            frase = (f"viento moderado{dir_txt} que hará que se "
                     "sienta más frío")
        else:
            frase = f"viento moderado{dir_txt} que refrescará el ambiente"
    else:
        # Viento ligero (10-20 km/h): solo si trae frío del norte o
        # arrastra lluvia; si no, no aporta nada y se omite.
        if direccion in ("NORTE", "NORESTE") \
                and media is not None and media <= 18:
            frase = (f"viento ligero{dir_txt} que hará que se "
                     "sienta más frío")
        elif prob >= 60:
            frase = "viento ligero que arrastrará la lluvia"
        else:
            return None

    if rafaga is not None and rafaga >= RAFAGA_FUERTE_KMH:
        frase += f", con ráfagas de hasta {rafaga:.0f} km/h"
    return frase


# ---------------------------------------------------------------------------
# Temperatura (sensación primero)
# ---------------------------------------------------------------------------

def frase_temperatura(bloque):
    """
    Frase sobre la temperatura de un bloque: sensación primero
    ("hará frío, unos 15 °C"). El rango mín/máx solo se cuenta
    cuando dentro del bloque hay un cambio de 5 °C o más.
    """
    media = bloque.get('temp_media')
    if media is None:
        return None
    sens = bloque.get('sensacion_media')
    referencia = sens if sens is not None else media

    if referencia < 12:
        palabra = "mucho frío"
    elif referencia < 16:
        palabra = "frío"
    elif referencia < 19:
        palabra = "fresco"
    elif referencia <= 25:
        palabra = "agradable"
    elif referencia <= 30:
        palabra = "caluroso"
    elif referencia <= 35:
        palabra = "mucho calor"
    else:
        palabra = "calor extremo"

    if palabra == "agradable":
        frase = f"ambiente agradable, unos {media:.0f} °C"
    else:
        frase = f"hará {palabra}, unos {media:.0f} °C"

    tmin = bloque.get('temp_min')
    tmax = bloque.get('temp_max')
    if tmin is not None and tmax is not None \
            and (tmax - tmin) >= RANGO_TEMP_RELEVANTE_C:
        frase += f" (mín. {tmin:.0f}°, máx. {tmax:.0f}°)"

    if sens is not None and abs(sens - media) >= DIFERENCIA_SENSACION_C:
        frase += f", pero se sentirá de {sens:.0f} °C"
    return frase


# ---------------------------------------------------------------------------
# Presión (una línea para todo el día, no por bloque)
# ---------------------------------------------------------------------------

def frase_presion_dia(bloques):
    """
    Frase sobre la presión para todo el día, o None si está normal
    y estable: una presión entre 1005 y 1025 hPa sin cambios no le
    dice nada a nadie. Solo aparece cuando baja o sube lo suficiente
    para anunciar algo.
    """
    presiones = [b.get('presion_media') for b in bloques
                 if b.get('presion_media') is not None]
    if len(presiones) < 2:
        return None
    tendencia = presiones[-1] - presiones[0]
    if tendencia <= -PRESION_CAMBIO_HPA:
        return "La presión viene bajando: la lluvia se mantendrá."
    if tendencia >= PRESION_CAMBIO_HPA:
        return "La presión viene subiendo: el tiempo tiende a mejorar."
    if min(presiones) < PRESION_NORMAL_MIN_HPA:
        return ("Presión baja: ambiente inestable, puede llover en "
                "cualquier momento.")
    if min(presiones) > PRESION_NORMAL_MAX_HPA:
        return "Presión alta y estable: tiempo tranquilo."
    return None


# ---------------------------------------------------------------------------
# Resumen del día, advertencia de confianza y recomendación
# ---------------------------------------------------------------------------

def resumen_dia(bloques):
    """
    Una frase decisiva sobre el día: "Hoy en Tempoal: día de
    lluvias con frío." Se arma con lo más importante (lluvia y
    temperatura) sin listar números.
    """
    if not bloques:
        return "Hoy en Tempoal: sin datos del pronóstico."
    probs = [(_num(b.get('prob_max')) or 0) for b in bloques]
    n_lluvia = sum(1 for p in probs if p >= 70)
    max_prob = max(probs) if probs else 0
    tmax_dia = max((b.get('temp_max') for b in bloques
                    if b.get('temp_max') is not None), default=None)
    tmin_dia = min((b.get('temp_min') for b in bloques
                    if b.get('temp_min') is not None), default=None)

    if n_lluvia >= 2:
        base = "día de lluvias"
    elif n_lluvia == 1:
        nombre = next(_nombre_frase(b) for b in bloques
                      if (_num(b.get('prob_max')) or 0) >= 70)
        base = f"lluvia en la {nombre}"
    elif max_prob >= 40:
        base = "día con chubascos ocasionales"
    elif max_prob >= 20:
        base = "día nublado con alguna llovizna"
    else:
        nubes = [b.get('nubosidad_media') for b in bloques
                 if b.get('nubosidad_media') is not None]
        nub_media = sum(nubes) / len(nubes) if nubes else 50
        if nub_media >= 70:
            base = "día nublado y seco"
        elif nub_media <= 30:
            base = "día despejado"
        else:
            base = "día seco"

    cualif = ""
    if tmax_dia is not None and tmax_dia >= 35:
        cualif = " con mucho calor"
    elif tmax_dia is not None and tmax_dia >= 32:
        cualif = " con calor"
    elif (tmin_dia is not None and tmin_dia <= 12) \
            or (tmax_dia is not None
                and tmax_dia <= ESPECIAL_TEMP_MAX_FRIO_C):
        cualif = " con frío"
    return f"Hoy en Tempoal: {base}{cualif}."


def advertencia_confianza(confianza):
    """
    Solo cuando el pronóstico es poco seguro (BAJA): el lector debe
    saber que las condiciones pueden cambiar. Con MEDIA o ALTA no
    hay nada que advertir.
    """
    if confianza == "BAJA":
        return "El pronóstico es poco seguro hoy: las condiciones pueden cambiar."
    return None


def recomendacion_practica(bloques):
    """
    Cierre práctico: qué hacer con este pronóstico. Solo se
    recomienda lo que de verdad aplica hoy (paraguas, abrigarse,
    asegurar objetos...). Si nada aplica, no hay cierre.
    """
    if not bloques:
        return None
    recs = []

    lluviosos = [_nombre_frase(b) for b in bloques
                 if (_num(b.get('prob_max')) or 0) >= 70]
    if lluviosos:
        if len(lluviosos) >= 3:
            recs.append("Lleva paraguas y maneja con cuidado: "
                        "lloverá todo el día.")
        else:
            recs.append("Lleva paraguas y maneja con cuidado por la "
                        "lluvia de la " + " y la ".join(lluviosos) + ".")

    tormenta = any(b.get('codigo') in (95, 96, 99) for b in bloques)
    if tormenta:
        recs.append("Evita salir durante la tormenta.")

    viento_fuerte = any(
        (b.get('viento_max') or 0) >= VIENTO_FUERTE_KMH
        or (b.get('rafaga_max') or 0) >= 50 for b in bloques)
    if viento_fuerte:
        recs.append("Asegura objetos sueltos y ten cuidado con ramas.")

    tmin_dia = min((b.get('temp_min') for b in bloques
                    if b.get('temp_min') is not None), default=None)
    if tmin_dia is not None and tmin_dia <= ESPECIAL_TEMP_MIN_FRIO_C:
        recs.append("Abrígate bien, la mañana estará muy fría.")

    tmax_dia = max((b.get('temp_max') for b in bloques
                    if b.get('temp_max') is not None), default=None)
    if tmax_dia is not None and tmax_dia >= 35:
        recs.append("Toma agua y evita el sol de mediodía.")

    if not recs:
        return None
    return " ".join(recs[:2])


# ---------------------------------------------------------------------------
# Comparación especial (solo en casos excepcionales)
# ---------------------------------------------------------------------------

def comparacion_especial(bloques, daily):
    """
    Una frase de referencia para un día fuera de lo común, o None.

    Disparadores (día excepcional): lluvia >= 90% en los 3 bloques,
    viento máximo >= 50 km/h, máxima del día <= 18 °C, mínima <=
    10 °C, lluvia acumulada >= 30 mm, o caída de presión >= 5 hPa.

    La frase sale de UNA de estas dos fuentes, y solo de estas:
    (a) un superlativo VERIFICADO contra la ventana de 7 días del
    propio pronóstico (los arreglos daily de Open-Meteo);
    (b) una referencia genérica local sin fecha ("como un norte
    fuerte", "frío poco común para Tempoal en esta época").
    Si el día es excepcional pero no hay superlativo verdadero ni
    referencia genérica segura, no se dice nada: mejor callar que
    inventar un evento, una fecha o un récord.
    """
    if not bloques:
        return None
    probs = [(_num(b.get('prob_max')) or 0) for b in bloques]
    lluvia_3 = len(probs) == 3 and all(p >= ESPECIAL_LLUVIA_BLOQUES
                                       for p in probs)
    viento_max_dia = max((b.get('viento_max') or 0) for b in bloques)
    tmax_dia = max((b.get('temp_max') for b in bloques
                    if b.get('temp_max') is not None), default=None)
    tmin_dia = min((b.get('temp_min') for b in bloques
                    if b.get('temp_min') is not None), default=None)
    lluvia_total = sum((b.get('lluvia_mm') or 0) for b in bloques)
    presiones = [b.get('presion_media') for b in bloques
                 if b.get('presion_media') is not None]
    caida_presion = (presiones[0] - presiones[-1]) \
        if len(presiones) >= 2 else 0

    disparador = None
    if lluvia_3:
        disparador = 'lluvia'
    elif viento_max_dia >= ESPECIAL_VIENTO_KMH:
        disparador = 'viento'
    elif tmin_dia is not None and tmin_dia <= ESPECIAL_TEMP_MIN_FRIO_C:
        disparador = 'frio'
    elif tmax_dia is not None and tmax_dia <= ESPECIAL_TEMP_MAX_FRIO_C:
        disparador = 'frio'
    elif lluvia_total >= ESPECIAL_LLUVIA_DIA_MM:
        disparador = 'lluvia'
    elif caida_presion >= ESPECIAL_CAIDA_PRESION_HPA:
        disparador = 'presion'
    if disparador is None:
        return None

    # (a) Superlativos verificados contra la ventana de 7 días.
    # Hoy es el índice 0 de los arreglos daily.
    daily = daily or {}
    tiempos = daily.get('time') or []
    if len(tiempos) >= 2:
        probs_dias = daily.get('precipitation_probability_max') or []
        maxs = daily.get('temperature_2m_max') or []
        vientos = daily.get('wind_speed_10m_max') or []
        lluvias = daily.get('precipitation_sum') or []
        if lluvia_3 and probs_dias \
                and probs_dias[0] == max(probs_dias):
            return "Es el día más lluvioso de la semana."
        if disparador == 'frio' and maxs and maxs[0] == min(maxs):
            return "Es el día más frío de los próximos 7 días."
        if disparador == 'viento' and vientos \
                and vientos[0] == max(vientos):
            return "Es el día con más viento de la semana."
        if disparador == 'lluvia' and lluvias \
                and lluvias[0] == max(lluvias):
            return "Es el día con más lluvia acumulada de la semana."

    # (b) Referencias genéricas locales, sin fecha ni evento.
    # Solo para los dos casos más claros; en los demás, silencio.
    if disparador == 'viento' and viento_max_dia >= ESPECIAL_VIENTO_KMH:
        return "Viento como de un norte fuerte."
    if disparador == 'frio' and tmin_dia is not None \
            and tmin_dia <= ESPECIAL_TEMP_MIN_FRIO_C:
        return "Un frío poco común para Tempoal en esta época."
    return None


# ---------------------------------------------------------------------------
# Composición: un bloque y el día completo
# ---------------------------------------------------------------------------

def interpretar_bloque(bloque, contexto=None):
    """
    Texto interpretado de un bloque (mañana, tarde o noche): lluvia,
    temperatura y viento solo si causa algo. Empieza con mayúscula
    y termina con punto; el llamador pone la viñeta y el nombre.
    """
    partes = [frase_lluvia(bloque)]
    temperatura = frase_temperatura(bloque)
    if temperatura:
        partes.append(temperatura)
    viento = frase_viento(bloque)
    if viento:
        partes.append(viento)
    texto = ". ".join(p[:1].upper() + p[1:] if p else p for p in partes)
    return texto + "."


def interpretar_dia(bloques, daily=None, confianza=None):
    """
    Piezas del reporte del día, listas para armar el mensaje:
    resumen, advertencia de confianza, comparación especial,
    presión y recomendación práctica. Cada valor es None cuando
    no hay nada que decir.
    """
    return {
        'resumen': resumen_dia(bloques),
        'advertencia': advertencia_confianza(confianza),
        'especial': comparacion_especial(bloques, daily or {}),
        'presion': frase_presion_dia(bloques),
        'recomendacion': recomendacion_practica(bloques),
    }

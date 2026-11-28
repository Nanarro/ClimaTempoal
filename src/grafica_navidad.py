"""
Gráfica de la distribución de la mínima para la noche de Navidad,
estilo MeteoAlert.

Un solo gráfico con la distribución de la temperatura mínima del
25 de diciembre (la mínima cae en la madrugada, es decir, la noche
24→25), calculada con el ensemble GFS (31 miembros: 30 perturbados
+ control, alcance 35 días), en 10 rangos como MeteoAlert.

Decisión de modelo: el ensemble ECMWF (51 miembros) solo llega a
15 días, así que a finales de noviembre todavía no alcanza a Navidad
(30 días). El GFS Seamless es el único ensemble gratuito que llega
(35 días), por eso se usa aquí aunque tenga menos miembros y menos
resolución que el ECMWF. Se usa SOLO para esta gráfica, no para el
pronóstico diario.

Advertencia honesta: a 30 días la incertidumbre es ENORME. La
distribución se afina al acercarse diciembre. Por eso la gráfica lo
dice en el pie y los días sin datos no se inventan: si el 25 de
diciembre no está en los datos, no hay gráfica.

Los umbrales de frío (12 °C y 10 °C) se conservan solo para el
resumen que usan el caption y el narrador (P(<12) y P(<10) del
25 de diciembre); la gráfica ya no dibuja umbrales por día.

La gráfica es best-effort: si no hay datos o algo falla, devuelve
None y el reporte y la tarjeta diaria salen igual.
"""

import os
from datetime import date, timedelta

from PIL import Image, ImageDraw, ImageFont

from .utils import logger, obtener_hora_mexico

# Umbrales de frío para Tempoal (°C): se conservan para el resumen
# de la distribución (P(<12) y P(<10)) que usan el caption y el
# narrador. Las mínimas de diciembre en Tempoal rondan 13-16 °C.
UMBRAL_FRIO_C = 12.0
UMBRAL_MUY_FRIO_C = 10.0

# Alcance del ensemble GFS en días (lo que cubre la Ensemble API)
DIAS_ALCANCE_NAVIDAD = 35

# Un miembro "dice que llueve" esa noche si su precipitación del
# 25 de diciembre supera esto (mm). 0.1 mm es el mínimo que
# registra una estación: menos que eso es rocío, no lluvia.
UMBRAL_LLUVIA_NOCHE_MM = 0.1

# Dimensiones y paleta (misma que la tarjeta diaria, tarjeta.py)
ANCHO = 1200
ALTO = 720
COLOR_FONDO = (11, 21, 38)
COLOR_TEXTO = (255, 255, 255)
COLOR_TEXTO_SUAVE = (159, 179, 200)
COLOR_BORDE = (42, 63, 95)
COLOR_ACENTO = (214, 38, 61)       # Rojo MeteoAlert
COLOR_NAVIDAD = (242, 201, 76)     # Dorado: resalta el rango más probable
COLOR_REJILLA = (32, 48, 72)

# Rangos de la distribución (exactos como MeteoAlert): (etiqueta,
# predicado). Los bordes son [bajo, alto): 5 °C cae en "1–5°",
# 10 °C en "9–10°", 12 °C en "11–12°", 21 °C en "≥ 21°". Así todo
# valor cae en un solo rango, sin huecos.
RANGOS_MINIMA = [
    ("≤ 0°", lambda v: v <= 0),
    ("1–5°", lambda v: 0 < v < 6),
    ("6–8°", lambda v: 6 <= v < 9),
    ("9–10°", lambda v: 9 <= v < 11),
    ("11–12°", lambda v: 11 <= v < 13),
    ("13–14°", lambda v: 13 <= v < 15),
    ("15–16°", lambda v: 15 <= v < 17),
    ("17–18°", lambda v: 17 <= v < 19),
    ("19–20°", lambda v: 19 <= v < 21),
    ("≥ 21°", lambda v: v >= 21),
]

# Degradado frío→cálido (morado los rangos fríos, azul los medios,
# verde los cálidos), como MeteoAlert.
COLORES_RANGO = [
    (126, 34, 206), (147, 51, 234), (168, 85, 247), (129, 140, 248),
    (96, 165, 250), (59, 130, 246), (37, 99, 235), (14, 165, 233),
    (34, 197, 94), (22, 163, 74),
]


def _cargar_fuente(negrita=False, tamano=24):
    """Carga DejaVu Sans (presente en ubuntu-latest) o la fuente por defecto."""
    nombre = "DejaVuSans-Bold.ttf" if negrita else "DejaVuSans.ttf"
    candidatos = [
        os.path.join("/usr/share/fonts/truetype/dejavu", nombre),
        os.path.join(os.path.expanduser("~"), ".fonts", nombre),
        nombre,
    ]
    for ruta in candidatos:
        try:
            return ImageFont.truetype(ruta, tamano)
        except (OSError, IOError):
            continue
    return ImageFont.load_default()


def temporada_navidad(hoy=None):
    """
    True si Navidad (25 de diciembre) cae dentro de los próximos
    35 días, es decir, si el ensemble GFS ya la alcanza.
    Hoy 25 de noviembre: sí (faltan 30 días). El 26 de diciembre: no.
    """
    hoy = hoy or obtener_hora_mexico().date()
    for anio in (hoy.year, hoy.year + 1):
        navidad = date(anio, 12, 25)
        delta = (navidad - hoy).days
        if 0 <= delta <= DIAS_ALCANCE_NAVIDAD:
            return True
    return False


def _claves_miembros_diarias(daily, variable):
    """Claves '<variable>_memberNN' ordenadas (miembros perturbados)."""
    prefijo = variable + "_member"
    return sorted(k for k in (daily or {}) if k.startswith(prefijo))


def _valores_miembros(daily, variable, indice):
    """
    Valores de una variable diaria en un índice: el control (clave
    sin sufijo) más los miembros perturbados que tengan dato.
    """
    valores = []
    for clave in [variable] + _claves_miembros_diarias(daily, variable):
        arr = daily.get(clave) or []
        if indice < len(arr) and arr[indice] is not None:
            valores.append(arr[indice])
    return valores


def frase_rango_minima(etiqueta):
    """
    Frasea un rango en palabras: '15–16°' -> 'entre 15 y 16 °C',
    '≤ 0°' -> 'de 0 °C o menos', '≥ 21°' -> 'de 21 °C o más'.
    """
    etiqueta = (etiqueta or "").strip()
    if etiqueta.startswith("≤"):
        return "de 0 °C o menos"
    if etiqueta.startswith("≥"):
        return "de 21 °C o más"
    partes = etiqueta.replace("°", "").split("–")
    if len(partes) == 2:
        return f"entre {partes[0].strip()} y {partes[1].strip()} °C"
    return etiqueta


def distribucion_minima_navidad(datos_ensemble):
    """
    Distribución de la mínima del 25 de diciembre por miembro GFS.

    La mínima diaria del 25 de diciembre cae en la madrugada, es
    decir, es la mínima de la noche 24→25. Para cada uno de los 10
    rangos se cuenta qué fracción de miembros (control + perturbados
    con dato) cae en él.

    Devuelve un dict con:
    - 'fecha': el 25 de diciembre (date).
    - 'distribucion': lista de 10 (etiqueta, %) en el orden de los
      rangos; los % son redondeados y suman ~100%.
    - 'mas_probable': (etiqueta, %) del rango con más miembros.
    - 'n_miembros': cuántos miembros tenían dato ese día.
    - 'prob_frio': % con mínima < 12 °C; 'prob_muy_frio': % < 10 °C.
    - 'prob_lluvia': % con lluvia > 0.1 mm ese día, o None si no
      hay dato de lluvia (no se inventa nada).

    Devuelve None si el 25 de diciembre no está en los datos o
    ningún miembro tiene dato: en ese caso no hay gráfica.
    """
    daily = (datos_ensemble or {}).get('daily', {}) or {}
    tiempos = daily.get('time', []) or []
    indice_25 = None
    fecha_25 = None
    for i, t in enumerate(tiempos):
        try:
            dia = date.fromisoformat(str(t)[:10])
        except (ValueError, TypeError):
            continue
        if dia.month == 12 and dia.day == 25:
            indice_25 = i
            fecha_25 = dia
            break
    if indice_25 is None:
        return None
    valores = _valores_miembros(daily, 'temperature_2m_min', indice_25)
    if not valores:
        return None
    n = len(valores)
    distribucion = []
    for etiqueta, en_rango in RANGOS_MINIMA:
        cuenta = sum(1 for v in valores if en_rango(v))
        distribucion.append((etiqueta, round(100 * cuenta / n)))
    mas_probable = max(distribucion, key=lambda par: par[1])
    lluvias = _valores_miembros(daily, 'precipitation_sum', indice_25)
    if lluvias:
        prob_lluvia = round(
            100 * sum(1 for v in lluvias if v > UMBRAL_LLUVIA_NOCHE_MM)
            / len(lluvias))
    else:
        prob_lluvia = None
    return {
        'fecha': fecha_25,
        'distribucion': distribucion,
        'mas_probable': mas_probable,
        'n_miembros': n,
        'prob_frio': round(
            100 * sum(1 for v in valores if v < UMBRAL_FRIO_C) / n),
        'prob_muy_frio': round(
            100 * sum(1 for v in valores if v < UMBRAL_MUY_FRIO_C) / n),
        'prob_lluvia': prob_lluvia,
    }


def generar_grafica_navidad(distribucion, ruta_salida, n_miembros=None):
    """
    Dibuja la gráfica de distribución y la guarda como PNG.

    Args:
        distribucion: Dict de distribucion_minima_navidad.
        ruta_salida: Ruta del PNG a generar.
        n_miembros: Miembros del ensemble (para el pie); si es None se
            toma del dict.

    Returns:
        str: La ruta del PNG generado, o None si falló o no hay datos.
    """
    try:
        if not distribucion or not distribucion.get('distribucion'):
            logger.warning("Sin distribución para la gráfica de Navidad")
            return None
        pares = distribucion['distribucion']
        if n_miembros is None:
            n_miembros = distribucion.get('n_miembros') or 0
        mas_probable = distribucion.get('mas_probable')
        etiqueta_top = mas_probable[0] if mas_probable else None
        prob_lluvia = distribucion.get('prob_lluvia')

        img = Image.new("RGB", (ANCHO, ALTO), COLOR_FONDO)
        draw = ImageDraw.Draw(img)

        # Barra superior de acento
        draw.rectangle([0, 0, ANCHO, 10], fill=COLOR_ACENTO)

        # --- Encabezado ---
        fuente_titulo = _cargar_fuente(negrita=True, tamano=44)
        fuente_sub = _cargar_fuente(tamano=24)
        draw.text((28, 30), "¿Hará frío? Probabilidad de mínima",
                  font=fuente_titulo, fill=COLOR_TEXTO)
        draw.text(
            (28, 86),
            "Distribución de la mínima · Noche 24→25 dic · "
            "Tempoal, Veracruz",
            font=fuente_sub, fill=COLOR_TEXTO_SUAVE)
        if prob_lluvia is not None:
            draw.text(
                (28, 118),
                "Probabilidad de lluvia · Noche 24→25 dic: "
                f"{prob_lluvia}%",
                font=fuente_sub, fill=COLOR_TEXTO_SUAVE)

        draw.line([28, 164, ANCHO - 28, 164], fill=COLOR_BORDE, width=2)

        # --- Área de barras ---
        x0, x1 = 64, ANCHO - 28
        y_base, y_tope = 540, 196
        alto_plot = y_base - y_tope
        fuente_eje = _cargar_fuente(tamano=18)
        fuente_valor = _cargar_fuente(negrita=True, tamano=20)
        fuente_rango = _cargar_fuente(tamano=19)
        fuente_eje_x = _cargar_fuente(tamano=20)

        # Rejilla y etiquetas de 0/25/50/75/100%
        for pct in (0, 25, 50, 75, 100):
            y = y_base - alto_plot * pct / 100
            draw.line([x0, y, x1, y], fill=COLOR_REJILLA, width=1)
            texto = f"{pct}%"
            bbox = draw.textbbox((0, 0), texto, font=fuente_eje)
            draw.text((x0 - 8 - (bbox[2] - bbox[0]), y - 9), texto,
                      font=fuente_eje, fill=COLOR_TEXTO_SUAVE)

        n_rangos = len(pares)
        ancho_grupo = (x1 - x0) / n_rangos
        ancho_barra = int(ancho_grupo * 0.58)
        # Última etiqueta de % dibujada (x0, x1, y0, y1): con 10
        # rangos los grupos miden ~110 px y una etiqueta "42%" ~40 px,
        # así que no deberían chocar; se conserva la comprobación por
        # si un día dos rangos vecinos tienen % altos y parecidos.
        ultima_etiqueta = None
        for j, (etiqueta, pct) in enumerate(pares):
            gx = x0 + j * ancho_grupo
            cx = gx + ancho_grupo / 2
            color = COLORES_RANGO[j % len(COLORES_RANGO)]
            altura = alto_plot * (pct or 0) / 100
            bx0 = cx - ancho_barra / 2
            bx1 = cx + ancho_barra / 2
            if altura > 0:
                draw.rounded_rectangle(
                    [bx0, y_base - altura, bx1, y_base],
                    radius=4, fill=color)
            if etiqueta == etiqueta_top and altura > 0:
                # El rango más probable lleva contorno dorado
                draw.rounded_rectangle(
                    [bx0 - 2, y_base - altura - 2, bx1 + 2, y_base],
                    radius=5, outline=COLOR_NAVIDAD, width=3)
            # % encima de la barra (siempre, aunque sea 0%)
            texto = f"{pct or 0}%"
            bbox = draw.textbbox((0, 0), texto, font=fuente_valor)
            ancho_txt = bbox[2] - bbox[0]
            alto_txt = bbox[3] - bbox[1]
            ex0 = cx - ancho_txt / 2
            ex1 = cx + ancho_txt / 2
            ey0 = y_base - altura - 30
            ey1 = ey0 + alto_txt
            choca = (
                ultima_etiqueta is not None
                and ex0 < ultima_etiqueta[1] + 4
                and ex1 > ultima_etiqueta[0] - 4
                and ey0 < ultima_etiqueta[3]
                and ey1 > ultima_etiqueta[2])
            if not choca:
                draw.text((ex0, ey0), texto, font=fuente_valor,
                          fill=COLOR_TEXTO)
                ultima_etiqueta = (ex0, ex1, ey0, ey1)
            # Etiqueta del rango bajo la barra
            bbox = draw.textbbox((0, 0), etiqueta, font=fuente_rango)
            draw.text((cx - (bbox[2] - bbox[0]) / 2, y_base + 10),
                      etiqueta, font=fuente_rango,
                      fill=COLOR_NAVIDAD if etiqueta == etiqueta_top
                      else COLOR_TEXTO_SUAVE)

        # Eje base y título del eje X
        draw.line([x0, y_base, x1, y_base], fill=COLOR_BORDE, width=2)
        titulo_eje = "Temperatura mínima (°C)"
        bbox = draw.textbbox((0, 0), titulo_eje, font=fuente_eje_x)
        draw.text(((ANCHO - (bbox[2] - bbox[0])) / 2, y_base + 42),
                  titulo_eje, font=fuente_eje_x, fill=COLOR_TEXTO_SUAVE)

        # --- Pie ---
        fuente_pie = _cargar_fuente(tamano=18)
        hora_gen = obtener_hora_mexico().strftime("%H:%M")
        draw.text((28, ALTO - 66),
                  f"Fuente: Open-Meteo · Ensemble GFS ({n_miembros} "
                  f"miembros) · Generado {hora_gen} h · "
                  "Protección Civil Tempoal",
                  font=fuente_pie, fill=COLOR_TEXTO_SUAVE)
        fecha_25 = distribucion.get('fecha')
        hoy = obtener_hora_mexico().date()
        if fecha_25 is not None:
            dias = (fecha_25 - hoy).days
            if dias > 0:
                advertencia = (
                    f"A {dias} días de Navidad la incertidumbre es muy "
                    "alta: la distribución se afina al acercarse "
                    "diciembre.")
            else:
                advertencia = (
                    "La fecha ya está encima: la distribución es mucho "
                    "más fiable que hace semanas.")
        else:
            advertencia = (
                "A semanas de Navidad la incertidumbre es muy alta: la "
                "distribución se afina al acercarse diciembre.")
        draw.text((28, ALTO - 40), advertencia,
                  font=fuente_pie, fill=COLOR_TEXTO_SUAVE)

        img.save(ruta_salida, format="PNG")
        logger.info(f"✅ Gráfica de Navidad generada: {ruta_salida}")
        return ruta_salida

    except Exception as e:
        logger.error(f"Error generando gráfica de Navidad: {e}")
        import traceback
        traceback.print_exc()
        return None

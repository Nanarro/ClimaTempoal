"""
Gráfica de probabilidad de frío rumbo a Navidad, estilo MeteoAlert.

Gráfico de barras con la probabilidad de temperatura mínima fría por
día, calculada con el ensemble GFS (31 miembros, alcance 35 días):
para cada día, la fracción de miembros cuya mínima pronosticada queda
por debajo del umbral de frío.

Decisión de modelo: el ensemble ECMWF (51 miembros) solo llega a
15 días, así que el 25 de noviembre todavía no alcanza a Navidad
(30 días). El GFS Seamless es el único ensemble gratuito que llega
(35 días), por eso se usa aquí aunque tenga menos miembros y menos
resolución que el ECMWF. Se usa SOLO para esta gráfica, no para el
pronóstico diario.

Advertencia honesta: a 30 días la incertidumbre es ENORME. Las
probabilidades de los primeros días son poco informativas y se afinan
al acercarse diciembre. Por eso la gráfica lo dice en el pie y los
días sin datos no se inventan: se marcan "sin datos".

Umbrales (Tempoal, donde las mínimas de diciembre rondan 13-16 °C):
- Frío: mínima < 12 °C (más frío de lo habitual en diciembre).
- Muy frío: mínima < 10 °C (frío notable, madrugada de chamarra).

La gráfica es best-effort: si no hay datos o algo falla, devuelve
None y el reporte y la tarjeta diaria salen igual.
"""

import os
from datetime import date, timedelta

from PIL import Image, ImageDraw, ImageFont

from .utils import logger, obtener_hora_mexico

# Umbrales de frío para Tempoal (°C)
UMBRAL_FRIO_C = 12.0
UMBRAL_MUY_FRIO_C = 10.0

# Alcance del ensemble GFS en días (lo que cubre la Ensemble API)
DIAS_ALCANCE_NAVIDAD = 35

# Dimensiones y paleta (misma que la tarjeta diaria, tarjeta.py)
ANCHO = 1200
ALTO = 720
COLOR_FONDO = (11, 21, 38)
COLOR_TEXTO = (255, 255, 255)
COLOR_TEXTO_SUAVE = (159, 179, 200)
COLOR_BORDE = (42, 63, 95)
COLOR_ACENTO = (214, 38, 61)       # Rojo MeteoAlert
COLOR_BARRA_FRIO = (78, 168, 222)      # Azul claro: P(mín < 12 °C)
COLOR_BARRA_MUY_FRIO = (47, 128, 237)  # Azul fuerte: P(mín < 10 °C)
COLOR_SIN_DATOS = (52, 68, 92)
COLOR_NAVIDAD = (242, 201, 76)     # Dorado para el 25 de diciembre
COLOR_REJILLA = (32, 48, 72)

MESES_CORTO = {
    1: "ENE", 2: "FEB", 3: "MAR", 4: "ABR", 5: "MAY", 6: "JUN",
    7: "JUL", 8: "AGO", 9: "SEP", 10: "OCT", 11: "NOV", 12: "DIC",
}


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


def rango_navidad(hoy=None):
    """
    (inicio, fin) del periodo a graficar: de mañana al 25 de diciembre.
    Devuelve None fuera de temporada.
    """
    hoy = hoy or obtener_hora_mexico().date()
    for anio in (hoy.year, hoy.year + 1):
        navidad = date(anio, 12, 25)
        if 0 <= (navidad - hoy).days <= DIAS_ALCANCE_NAVIDAD:
            return (hoy + timedelta(days=1), navidad)
    return None


def _claves_miembros_diarias(daily, variable):
    """Claves '<variable>_memberNN' ordenadas (miembros perturbados)."""
    prefijo = variable + "_member"
    return sorted(k for k in (daily or {}) if k.startswith(prefijo))


def calcular_probabilidades_frio(datos_ensemble, fecha_inicio, fecha_fin,
                                 umbral=UMBRAL_FRIO_C,
                                 umbral_muy_frio=UMBRAL_MUY_FRIO_C):
    """
    Probabilidad de mínima fría por día, a partir del ensemble GFS.

    Para cada día entre fecha_inicio y fecha_fin (inclusive):
    - prob_frio: % de miembros con mínima < `umbral` (12 °C).
    - prob_muy_frio: % de miembros con mínima < `umbral_muy_frio` (10 °C).
    - n_miembros: cuántos miembros tenían dato ese día.
    - sin_datos: True si el día no tiene datos (no se inventa nada).

    Devuelve [] si no hay claves de miembro en los datos.
    """
    daily = (datos_ensemble or {}).get('daily', {}) or {}
    tiempos = daily.get('time', []) or []
    claves = _claves_miembros_diarias(daily, 'temperature_2m_min')
    if not claves:
        return []

    indice_por_fecha = {}
    for i, t in enumerate(tiempos):
        try:
            indice_por_fecha[date.fromisoformat(str(t)[:10])] = i
        except (ValueError, TypeError):
            continue

    resultado = []
    dia = fecha_inicio
    while dia <= fecha_fin:
        i = indice_por_fecha.get(dia)
        if i is None:
            resultado.append({
                'fecha': dia, 'sin_datos': True,
                'prob_frio': None, 'prob_muy_frio': None, 'n_miembros': 0,
            })
            dia += timedelta(days=1)
            continue
        valores = []
        for k in claves:
            arr = daily.get(k) or []
            if i < len(arr) and arr[i] is not None:
                valores.append(arr[i])
        if not valores:
            resultado.append({
                'fecha': dia, 'sin_datos': True,
                'prob_frio': None, 'prob_muy_frio': None, 'n_miembros': 0,
            })
        else:
            n = len(valores)
            resultado.append({
                'fecha': dia,
                'sin_datos': False,
                'prob_frio': round(
                    100 * sum(1 for v in valores if v < umbral) / n),
                'prob_muy_frio': round(
                    100 * sum(1 for v in valores if v < umbral_muy_frio) / n),
                'n_miembros': n,
            })
        dia += timedelta(days=1)
    return resultado


def generar_grafica_navidad(probabilidades, ruta_salida,
                            umbral=UMBRAL_FRIO_C,
                            umbral_muy_frio=UMBRAL_MUY_FRIO_C,
                            n_miembros=None):
    """
    Dibuja la gráfica de barras y la guarda como PNG.

    Args:
        probabilidades: Lista de dicts de calcular_probabilidades_frio.
        ruta_salida: Ruta del PNG a generar.
        umbral / umbral_muy_frio: Umbrales de frío (°C) que se grafican.
        n_miembros: Miembros del ensemble (para el pie); si es None se
            toma del primer día con datos.

    Returns:
        str: La ruta del PNG generado, o None si falló o no hay datos.
    """
    try:
        if not probabilidades:
            logger.warning("Sin probabilidades para la gráfica de Navidad")
            return None
        if n_miembros is None:
            con_datos = [p for p in probabilidades if not p.get('sin_datos')]
            n_miembros = con_datos[0].get('n_miembros') if con_datos else 0

        img = Image.new("RGB", (ANCHO, ALTO), COLOR_FONDO)
        draw = ImageDraw.Draw(img)

        # Barra superior de acento
        draw.rectangle([0, 0, ANCHO, 10], fill=COLOR_ACENTO)

        # --- Encabezado ---
        fuente_titulo = _cargar_fuente(negrita=True, tamano=44)
        fuente_sub = _cargar_fuente(tamano=24)
        draw.text((28, 30), "¿FRÍO EN NAVIDAD?", font=fuente_titulo,
                  fill=COLOR_TEXTO)
        draw.text(
            (28, 86),
            f"Probabilidad de mínima < {umbral:.0f} °C rumbo al 25 de "
            f"diciembre  •  Tempoal, Veracruz",
            font=fuente_sub, fill=COLOR_TEXTO_SUAVE)

        # Leyenda
        fuente_leyenda = _cargar_fuente(negrita=True, tamano=20)
        y_ley = 132
        draw.rounded_rectangle([28, y_ley, 52, y_ley + 20], radius=4,
                               fill=COLOR_BARRA_FRIO)
        draw.text((60, y_ley - 2), f"Mín. < {umbral:.0f} °C",
                  font=fuente_leyenda, fill=COLOR_TEXTO)
        draw.rounded_rectangle([268, y_ley, 292, y_ley + 20], radius=4,
                               fill=COLOR_BARRA_MUY_FRIO)
        draw.text((300, y_ley - 2), f"Mín. < {umbral_muy_frio:.0f} °C",
                  font=fuente_leyenda, fill=COLOR_TEXTO)
        draw.text((560, y_ley - 2), "★ 25 de diciembre",
                  font=fuente_leyenda, fill=COLOR_NAVIDAD)

        draw.line([28, 168, ANCHO - 28, 168], fill=COLOR_BORDE, width=2)

        # --- Área de barras ---
        x0, x1 = 64, ANCHO - 28
        y_base, y_tope = 560, 196
        alto_plot = y_base - y_tope
        fuente_eje = _cargar_fuente(tamano=18)
        fuente_valor = _cargar_fuente(negrita=True, tamano=18)
        fuente_dia = _cargar_fuente(tamano=17)

        # Rejilla y etiquetas de 0/25/50/75/100%
        for pct in (0, 25, 50, 75, 100):
            y = y_base - alto_plot * pct / 100
            draw.line([x0, y, x1, y], fill=COLOR_REJILLA, width=1)
            texto = f"{pct}%"
            bbox = draw.textbbox((0, 0), texto, font=fuente_eje)
            draw.text((x0 - 8 - (bbox[2] - bbox[0]), y - 9), texto,
                      font=fuente_eje, fill=COLOR_TEXTO_SUAVE)

        n_dias = len(probabilidades)
        ancho_grupo = (x1 - x0) / n_dias
        ancho_barra = max(4, int(ancho_grupo * 0.36))
        # Última etiqueta de % dibujada (x0, x1, y0, y1): con ~30 días
        # los grupos miden ~37 px y una etiqueta "30%" ~38 px, así que
        # dos días seguidos con % parecidos se empalmaban (se veía
        # "30%30%" cerca del 19-20 dic). Si la siguiente etiqueta
        # chocaría con la anterior, se omite: el valor sigue en la
        # altura de la barra y la gráfica queda legible.

        ultima_etiqueta = None
        for j, dia in enumerate(probabilidades):
            gx = x0 + j * ancho_grupo
            cx = gx + ancho_grupo / 2
            fecha = dia['fecha']
            es_navidad = fecha.month == 12 and fecha.day == 25
            if dia.get('sin_datos'):
                # Día sin datos: barrita gris corta, no se inventa nada
                draw.rounded_rectangle(
                    [cx - ancho_barra, y_base - 14,
                     cx + ancho_barra, y_base],
                    radius=3, fill=COLOR_SIN_DATOS)
                draw.text((cx - 12, y_base - 34), "s/d",
                          font=fuente_valor, fill=COLOR_TEXTO_SUAVE)
            else:
                for k, (prob, color) in enumerate((
                        (dia['prob_frio'], COLOR_BARRA_FRIO),
                        (dia['prob_muy_frio'], COLOR_BARRA_MUY_FRIO))):
                    altura = alto_plot * (prob or 0) / 100
                    bx0 = cx - ancho_barra - 2 + k * (ancho_barra + 4)
                    bx1 = bx0 + ancho_barra
                    if altura > 0:
                        draw.rounded_rectangle(
                            [bx0, y_base - altura, bx1, y_base],
                            radius=3, fill=color)
                    if es_navidad:
                        draw.rounded_rectangle(
                            [bx0 - 2, y_base - altura - 2, bx1 + 2, y_base],
                            radius=4, outline=COLOR_NAVIDAD, width=2)
                if (dia['prob_frio'] or 0) >= 20:
                    texto = f"{dia['prob_frio']}%"
                    bbox = draw.textbbox((0, 0), texto, font=fuente_valor)
                    ancho_txt = bbox[2] - bbox[0]
                    alto_txt = bbox[3] - bbox[1]
                    ex0 = cx - ancho_txt / 2
                    ex1 = cx + ancho_txt / 2
                    ey0 = y_base - alto_plot * dia['prob_frio'] / 100 - 26
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
            # Etiqueta de fecha cada 5 días y siempre en Navidad
            if j % 5 == 0 or es_navidad:
                etiqueta = f"{fecha.day} {MESES_CORTO[fecha.month]}"
                bbox = draw.textbbox((0, 0), etiqueta, font=fuente_dia)
                draw.text((cx - (bbox[2] - bbox[0]) / 2, y_base + 10),
                          etiqueta, font=fuente_dia,
                          fill=COLOR_NAVIDAD if es_navidad
                          else COLOR_TEXTO_SUAVE)

        # Eje base
        draw.line([x0, y_base, x1, y_base], fill=COLOR_BORDE, width=2)

        # --- Pie ---
        fuente_pie = _cargar_fuente(tamano=18)
        hora_gen = obtener_hora_mexico().strftime("%H:%M")
        draw.text((28, ALTO - 66),
                  f"Fuente: Open-Meteo · Ensemble GFS ({n_miembros} "
                  f"miembros) · Generado {hora_gen} h",
                  font=fuente_pie, fill=COLOR_TEXTO_SUAVE)
        draw.text((28, ALTO - 40),
                  "A 30 días la incertidumbre es muy alta: estas "
                  "probabilidades se afinan al acercarse diciembre.",
                  font=fuente_pie, fill=COLOR_TEXTO_SUAVE)

        img.save(ruta_salida, format="PNG")
        logger.info(f"✅ Gráfica de Navidad generada: {ruta_salida}")
        return ruta_salida

    except Exception as e:
        logger.error(f"Error generando gráfica de Navidad: {e}")
        import traceback
        traceback.print_exc()
        return None

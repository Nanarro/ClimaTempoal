"""
Generación de la tarjeta diaria de pronóstico (imagen) estilo MeteoAlert.

Dibuja con Pillow una tarjeta oscura con 3 paneles (mañana / tarde / noche),
cada uno con temperatura, sensación térmica, probabilidad de lluvia, viento,
presión y una etiqueta corta, más la barra de nivel de confianza.

No depende de ningún asset externo: usa las fuentes DejaVu presentes en los
runners ubuntu-latest y el logo del repo si está disponible.
"""

import os

from PIL import Image, ImageDraw, ImageFont

from .formato import (
    etiqueta_bloque,
    nivel_confianza,
    obtener_bloques_diarios,
)
from .utils import DIAS_ESP, MESES_ESP, logger, obtener_hora_mexico

# Dimensiones de la tarjeta
ANCHO = 1200
ALTO = 800

# Paleta (estilo oscuro tipo MeteoAlert)
COLOR_FONDO = (11, 21, 38)
COLOR_PANEL = (22, 39, 63)
COLOR_BORDE_PANEL = (42, 63, 95)
COLOR_TEXTO = (255, 255, 255)
COLOR_TEXTO_SUAVE = (159, 179, 200)
COLOR_ACENTO = (214, 38, 61)       # Rojo MeteoAlert
COLOR_ETIQUETA_LLUVIA = (47, 128, 237)
COLOR_ETIQUETA_NORTE = (33, 158, 188)
COLOR_ETIQUETA_NUBLADO = (90, 107, 124)
COLOR_ETIQUETA_DESPEJADO = (242, 201, 76)
COLOR_CONFIANZA_BAJA = (242, 153, 74)
COLOR_CONFIANZA_MEDIA = (242, 201, 76)
COLOR_CONFIANZA_ALTA = (46, 204, 113)
COLOR_SEGMENTO_VACIO = (52, 68, 92)

# Glifos DejaVu disponibles (sin emoji): sol, nube, paraguas, lluvia, nieve
GLIFOS_CLIMA = {
    0: "☀",    # Despejado
    1: "☀",    # Principalmente despejado
    2: "☁",    # Parcialmente nublado
    3: "☁",    # Nublado
    45: "☁",   # Niebla
    48: "☁",   # Niebla con escarcha
    51: "☂",   # Llovizna ligera
    53: "☂",   # Llovizna moderada
    55: "☔",   # Llovizna densa
    61: "☂",   # Lluvia ligera
    63: "☔",   # Lluvia moderada
    65: "☔",   # Lluvia intensa
    71: "❄",   # Nevada ligera
    73: "❄",   # Nevada moderada
    75: "❄",   # Nevada intensa
    80: "☔",   # Chubascos ligeros
    81: "☔",   # Chubascos moderados
    82: "☔",   # Chubascos violentos
    95: "☔",   # Tormenta
    96: "☔",   # Tormenta con granizo ligero
    99: "☔",   # Tormenta con granizo fuerte
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


# Dirección abreviada para la fila de viento de la tarjeta (espacio corto)
DIRECCION_CORTA = {
    "NORTE": "N", "NORESTE": "NE", "ESTE": "E", "SURESTE": "SE",
    "SUR": "S", "SUROESTE": "SO", "OESTE": "O", "NOROESTE": "NO",
}


def _color_temperatura(temp):
    """Color del número de temperatura, como en MeteoAlert."""
    if temp is None:
        return COLOR_TEXTO_SUAVE
    if temp < 20:
        return (78, 168, 222)    # Azul (frío/fresco)
    if temp <= 25:
        return (111, 207, 151)   # Verde (templado)
    if temp <= 30:
        return (242, 153, 74)    # Naranja (cálido)
    return (235, 87, 87)         # Rojo (calor)


def _color_etiqueta(etiqueta):
    """Color de fondo de la franja de etiqueta del panel."""
    if "LLUVIA" in etiqueta:
        return COLOR_ETIQUETA_LLUVIA
    if "NORTE" in etiqueta:
        return COLOR_ETIQUETA_NORTE
    if etiqueta == "DESPEJADO":
        return COLOR_ETIQUETA_DESPEJADO
    return COLOR_ETIQUETA_NUBLADO


def _texto_centrado(draw, x_centro, y, texto, fuente, color):
    """
    Dibuja texto centrado horizontalmente en x_centro.

    Devuelve la coordenada Y de la parte inferior de la tinta, para que
    el siguiente elemento pueda separarse con un espacio real (con el
    ancla por defecto de Pillow, la Y que se pasa es la línea del
    ascendente, no la parte superior de la tinta).
    """
    bbox = draw.textbbox((0, 0), texto, font=fuente)
    ancho = bbox[2] - bbox[0]
    draw.text((x_centro - ancho / 2, y), texto, font=fuente, fill=color)
    return y + bbox[3]


def _fecha_tarjeta():
    """Fecha del día en formato 'MARTES 24 NOVIEMBRE 2026'."""
    ahora = obtener_hora_mexico()
    dia = DIAS_ESP[ahora.strftime("%A")]
    mes = MESES_ESP[ahora.month].upper()
    return f"{dia} {ahora.day} {mes} {ahora.year}"


def generar_tarjeta_diaria(datos, ruta_salida, ruta_logo=None):
    """
    Genera la tarjeta diaria de pronóstico y la guarda como PNG.

    Args:
        datos: Datos de Open-Meteo (dict con hourly/daily/current).
        ruta_salida: Ruta del PNG a generar.
        ruta_logo: Ruta opcional del logo a mostrar en el encabezado.

    Returns:
        str: La ruta del PNG generado, o None si falló.
    """
    try:
        bloques = obtener_bloques_diarios(datos)
        confianza, segmentos = nivel_confianza(bloques)
        color_confianza = {
            "BAJA": COLOR_CONFIANZA_BAJA,
            "MEDIA": COLOR_CONFIANZA_MEDIA,
            "ALTA": COLOR_CONFIANZA_ALTA,
        }[confianza]

        img = Image.new("RGB", (ANCHO, ALTO), COLOR_FONDO)
        draw = ImageDraw.Draw(img)

        # Barra superior de acento
        draw.rectangle([0, 0, ANCHO, 10], fill=COLOR_ACENTO)

        # --- Encabezado ---
        fuente_fecha = _cargar_fuente(negrita=True, tamano=40)
        fuente_sub = _cargar_fuente(tamano=24)
        draw.text((28, 34), _fecha_tarjeta(), font=fuente_fecha,
                  fill=COLOR_TEXTO)
        draw.text((28, 88), "TEMPOAL, VERACRUZ  •  MONITOREO PROTECCIÓN CIVIL",
                  font=fuente_sub, fill=COLOR_TEXTO_SUAVE)

        # Logo del repo (si existe) a la derecha del encabezado
        if ruta_logo and os.path.exists(ruta_logo):
            try:
                logo = Image.open(ruta_logo).convert("RGBA")
                logo.thumbnail((92, 92), Image.LANCZOS)
                img.paste(logo, (ANCHO - 28 - logo.width, 30), logo)
            except Exception as e:
                logger.warning(f"No se pudo cargar el logo: {e}")

        # Línea divisoria
        draw.line([28, 138, ANCHO - 28, 138], fill=COLOR_BORDE_PANEL, width=2)

        # --- Paneles (mañana / tarde / noche) ---
        margen = 24
        ancho_panel = (ANCHO - 2 * margen - 2 * 18) // 3
        y_panel = 158
        alto_panel = 470

        fuente_nombre = _cargar_fuente(negrita=True, tamano=32)
        fuente_horas = _cargar_fuente(tamano=20)
        fuente_glifo = _cargar_fuente(tamano=56)
        fuente_temp = _cargar_fuente(negrita=True, tamano=92)
        fuente_sensacion = _cargar_fuente(tamano=22)
        fuente_fila_etiqueta = _cargar_fuente(tamano=20)
        fuente_fila_valor = _cargar_fuente(negrita=True, tamano=24)
        fuente_tag = _cargar_fuente(negrita=True, tamano=24)

        for i, bloque in enumerate(bloques):
            x0 = margen + i * (ancho_panel + 18)
            x1 = x0 + ancho_panel
            xc = (x0 + x1) // 2

            draw.rounded_rectangle([x0, y_panel, x1, y_panel + alto_panel],
                                   radius=18, fill=COLOR_PANEL,
                                   outline=COLOR_BORDE_PANEL, width=2)

            y = y_panel + 18
            y = _texto_centrado(draw, xc, y, bloque['nombre'],
                                fuente_nombre, COLOR_TEXTO)
            y = _texto_centrado(draw, xc, y + 4, bloque['horas'],
                                fuente_horas, COLOR_TEXTO_SUAVE)

            # Glifo del clima (según código WMO dominante del bloque)
            glifo = GLIFOS_CLIMA.get(bloque.get('codigo'), "☁")
            y = _texto_centrado(draw, xc, y + 10, glifo,
                                fuente_glifo, COLOR_TEXTO_SUAVE)

            # Temperatura grande + sensación térmica
            temp = bloque.get('temp_media')
            texto_temp = f"{temp:.0f}°" if temp is not None else "--°"
            y = _texto_centrado(draw, xc, y + 6, texto_temp,
                                fuente_temp, _color_temperatura(temp))
            sensacion = bloque.get('sensacion_media')
            texto_sens = (f"Sensación térmica {sensacion:.0f}°"
                          if sensacion is not None else "Sensación térmica --°")
            y = _texto_centrado(draw, xc, y + 12, texto_sens,
                                fuente_sensacion, COLOR_TEXTO_SUAVE)

            # Línea divisoria del panel
            y += 18
            draw.line([x0 + 20, y, x1 - 20, y], fill=COLOR_BORDE_PANEL, width=2)
            y += 16

            # Filas de datos: lluvia, viento, presión
            filas = []
            prob = bloque.get('prob_max')
            filas.append(("PROB. LLUVIA",
                          f"{prob:.0f}%" if prob is not None else "--"))
            direccion = bloque.get('viento_dir') or "--"
            direccion_corta = DIRECCION_CORTA.get(direccion, direccion)
            vmin = bloque.get('viento_min')
            vmax = bloque.get('viento_max')
            if vmin is not None and vmax is not None and vmin != vmax:
                texto_viento = f"{direccion_corta} {vmin:.0f}–{vmax:.0f} km/h"
            elif vmax is not None:
                texto_viento = f"{direccion_corta} {vmax:.0f} km/h"
            else:
                texto_viento = direccion_corta
            filas.append(("VIENTO", texto_viento))
            presion = bloque.get('presion_media')
            filas.append(("PRESIÓN",
                          f"{presion:.0f} hPa" if presion is not None else "--"))

            for etiqueta, valor in filas:
                draw.text((x0 + 24, y), etiqueta,
                          font=fuente_fila_etiqueta, fill=COLOR_TEXTO_SUAVE)
                bbox = draw.textbbox((0, 0), valor, font=fuente_fila_valor)
                draw.text((x1 - 24 - (bbox[2] - bbox[0]), y - 2), valor,
                          font=fuente_fila_valor, fill=COLOR_TEXTO)
                y += 38

            # Franja de etiqueta en la parte inferior del panel
            etiqueta = etiqueta_bloque(bloque)
            color_tag = _color_etiqueta(etiqueta)
            color_texto_tag = (26, 26, 26) if etiqueta == "DESPEJADO" else COLOR_TEXTO
            draw.rounded_rectangle(
                [x0 + 14, y_panel + alto_panel - 62, x1 - 14,
                 y_panel + alto_panel - 14],
                radius=10, fill=color_tag)
            _texto_centrado(draw, xc, y_panel + alto_panel - 54, etiqueta,
                            fuente_tag, color_texto_tag)

        # --- Barra de nivel de confianza ---
        y_conf = y_panel + alto_panel + 28
        fuente_conf = _cargar_fuente(negrita=True, tamano=22)
        draw.text((28, y_conf), "NIVEL DE CONFIANZA DEL PRONÓSTICO",
                  font=fuente_conf, fill=COLOR_TEXTO_SUAVE)

        seg_ancho, seg_alto, seg_gap = 92, 26, 8
        x_seg = 560
        for s in range(4):
            color = color_confianza if s < segmentos else COLOR_SEGMENTO_VACIO
            draw.rounded_rectangle(
                [x_seg + s * (seg_ancho + seg_gap), y_conf,
                 x_seg + s * (seg_ancho + seg_gap) + seg_ancho,
                 y_conf + seg_alto],
                radius=6, fill=color)

        # Chip con el nivel (BAJA / MEDIA / ALTA)
        fuente_chip = _cargar_fuente(negrita=True, tamano=24)
        bbox = draw.textbbox((0, 0), confianza, font=fuente_chip)
        chip_ancho = (bbox[2] - bbox[0]) + 36
        x_chip = ANCHO - 28 - chip_ancho
        draw.rounded_rectangle([x_chip, y_conf - 4, ANCHO - 28,
                                y_conf + seg_alto + 4],
                               radius=8, fill=color_confianza)
        draw.text((x_chip + 18, y_conf), confianza, font=fuente_chip,
                  fill=(26, 26, 26) if confianza == "MEDIA" else COLOR_TEXTO)

        # --- Pie ---
        fuente_pie = _cargar_fuente(tamano=18)
        hora_gen = obtener_hora_mexico().strftime("%H:%M")
        _texto_centrado(draw, ANCHO // 2, ALTO - 40,
                        f"Fuente: Open-Meteo  •  Generado {hora_gen} h  •  "
                        f"Protección Civil Tempoal",
                        fuente_pie, COLOR_TEXTO_SUAVE)

        img.save(ruta_salida, format="PNG")
        logger.info(f"✅ Tarjeta diaria generada: {ruta_salida}")
        return ruta_salida

    except Exception as e:
        logger.error(f"Error generando tarjeta diaria: {e}")
        import traceback
        traceback.print_exc()
        return None

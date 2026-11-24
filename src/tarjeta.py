"""
Generación de la tarjeta diaria de pronóstico (imagen) estilo MeteoAlert.

Dibuja con Pillow una tarjeta oscura con 3 paneles (mañana / tarde / noche),
cada uno con foto de fondo según el clima, temperatura, sensación térmica,
probabilidad de lluvia, viento, presión y una etiqueta corta, más la barra
de nivel de confianza, un contador discreto de la próxima festividad y,
en diciembre, esferas navideñas en el encabezado.

Fotos en assets/fondos/ (10 de día + 5 de noche). Si falta una foto, el
panel usa el color sólido de siempre: la tarjeta nunca falla por eso.
"""

import os
from datetime import date

from PIL import Image, ImageDraw, ImageFont

from .formato import (
    etiqueta_bloque,
    nivel_confianza,
    obtener_bloques_diarios,
)
from .utils import DIAS_ESP, MESES_ESP, logger, obtener_hora_mexico

# Carpeta de fotos de fondo (relativa a este archivo: ../assets/fondos)
DIR_FONDOS = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "..", "assets", "fondos")

# Códigos WMO de tormenta eléctrica
CODIGOS_TORMENTA = {95, 96, 99}

# Equivalente nocturno de cada condición de día (solo existen 5 fotos
# de noche; el resto cae a la más parecida)
NOCHE_MAPA = {
    "tormenta": "noche_tormenta",
    "frente_frio": "noche_frente_frio",
    "chubascos": "noche_chubascos",
    "nublado": "noche_nublado",
    "despejado": "noche_despejado",
    "soleado": "noche_despejado",
    "calor": "noche_despejado",
    "calor_extremo": "noche_despejado",
    "viento": "noche_nublado",
    "sequia": "noche_despejado",
}

# Festividades con contador: (nombre, (mes, día), (mes, día desde el que
# se muestra), día final en que se sigue mostrando; por defecto el mismo
# día del evento). El contador aparece solo dentro de su ventana.
EVENTOS = [
    ("Halloween", (10, 31), (10, 1), (10, 31)),
    ("Día de Muertos", (11, 1), (10, 2), (11, 2)),
    ("Navidad", (12, 25), (12, 1), (12, 25)),
    ("Año Nuevo", (1, 1), (12, 26), (1, 1)),
]

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


def _color_lluvia(prob):
    """Color del % de lluvia, como en MeteoAlert: rojo alto, naranja medio,
    amarillo bajo, blanco muy bajo."""
    if prob is None:
        return COLOR_TEXTO
    if prob >= 70:
        return (235, 87, 87)     # Rojo
    if prob >= 50:
        return (242, 153, 74)    # Naranja
    if prob >= 20:
        return (242, 201, 76)    # Amarillo
    return COLOR_TEXTO


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


def _condicion_dia(bloque):
    """Condición de día del bloque, según sus datos.

    Prioridad: tormenta > frente frío (viento muy fuerte) > calor extremo
    > chubascos > sequía (semana casi sin lluvia y calor) > calor >
    viento > nublado > soleado > despejado.
    """
    codigo = bloque.get('codigo')
    prob = bloque.get('prob_max') or 0
    tmax = bloque.get('temp_max')
    tmedia = bloque.get('temp_media')
    vmax = bloque.get('viento_max')
    nub = bloque.get('nubosidad_media')
    lluvia_7d = bloque.get('lluvia_7d')
    if codigo in CODIGOS_TORMENTA:
        return 'tormenta'
    if vmax is not None and vmax >= 50:
        return 'frente_frio'
    if tmax is not None and tmax >= 40:
        return 'calor_extremo'
    if prob >= 60:
        return 'chubascos'
    if (lluvia_7d is not None and lluvia_7d < 2
            and tmax is not None and tmax >= 32):
        return 'sequia'
    if tmax is not None and tmax >= 35:
        return 'calor'
    if vmax is not None and vmax >= 30:
        return 'viento'
    if nub is not None and nub >= 75:
        return 'nublado'
    if prob >= 30:
        return 'chubascos'
    if tmedia is not None and tmedia >= 28 and (nub or 100) <= 40:
        return 'soleado'
    return 'despejado'


def seleccionar_fondo(bloque):
    """Ruta de la foto de fondo del panel, o None si no existe.

    El panel de noche usa la variante nocturna de la condición.
    """
    condicion = _condicion_dia(bloque)
    if bloque.get('nombre') == 'NOCHE':
        condicion = NOCHE_MAPA.get(condicion, condicion)
    ruta = os.path.join(DIR_FONDOS, f"{condicion}.jpg")
    return ruta if os.path.exists(ruta) else None


def texto_cuenta_regresiva(fecha=None):
    """Texto discreto con los días que faltan para la próxima festividad.

    Solo aparece dentro de la ventana de cada evento (p. ej. Navidad se
    muestra desde el 1 de diciembre; Día de Muertos desde 30 días antes).
    Devuelve None fuera de temporada. `fecha` es un date (para pruebas).
    """
    hoy = fecha or obtener_hora_mexico().date()
    mejor = None  # (dias_restantes, nombre, es_hoy)
    for nombre, (m_ev, d_ev), (m_ini, d_ini), (m_fin, d_fin) in EVENTOS:
        for anio in (hoy.year - 1, hoy.year, hoy.year + 1):
            try:
                evento = date(anio, m_ev, d_ev)
                inicio = date(anio, m_ini, d_ini)
                fin = date(anio, m_fin, d_fin)
            except ValueError:
                continue
            # La ventana puede cruzar el año (Año Nuevo: inicio en
            # diciembre del año anterior al evento)
            if inicio > evento:
                inicio = date(anio - 1, m_ini, d_ini)
            if inicio <= hoy <= fin:
                # Día de Muertos dura 2 días: el 2 de noviembre sigue
                # siendo "hoy" aunque el evento empezó el día 1
                dias = max((evento - hoy).days, 0)
                if mejor is None or dias < mejor[0]:
                    mejor = (dias, nombre, dias == 0)
    if mejor is None:
        return None
    dias, nombre, es_hoy = mejor
    if es_hoy:
        if nombre == "Día de Muertos":
            return "Hoy es Día de Muertos"
        return f"¡Hoy es {nombre}!"
    if dias == 1:
        return f"Falta 1 día para {nombre}"
    return f"Faltan {dias} días para {nombre}"


def _dibujar_esferas_navidad(draw):
    """Guirnalda discreta de esferas navideñas colgando del borde superior.

    Solo se dibuja en diciembre, en el hueco del encabezado entre la
    fecha y el logo, para no tapar ningún texto.
    """
    colores = [(214, 38, 61), (46, 204, 113), (242, 201, 76)]
    for i, x in enumerate((790, 860, 930, 1000)):
        largo = 12 + (i % 3) * 7
        draw.line([x, 10, x, 10 + largo], fill=(120, 130, 145), width=1)
        draw.ellipse([x - 8, 10 + largo, x + 8, 10 + largo + 16],
                     fill=colores[i % 3], outline=(255, 255, 255))
        draw.ellipse([x - 3, 10 + largo + 3, x + 1, 10 + largo + 7],
                     fill=(255, 255, 255))


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
        if not datos:
            logger.error("Sin datos meteorológicos para generar la tarjeta")
            return None
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

        # En diciembre, esferas navideñas discretas en el encabezado
        if obtener_hora_mexico().month == 12:
            _dibujar_esferas_navidad(draw)

        # --- Paneles (mañana / tarde / noche) ---
        margen = 24
        ancho_panel = (ANCHO - 2 * margen - 2 * 18) // 3
        y_panel = 158
        alto_panel = 470

        fuente_nombre = _cargar_fuente(negrita=True, tamano=32)
        fuente_horas = _cargar_fuente(tamano=20)
        fuente_glifo = _cargar_fuente(tamano=56)
        fuente_temp = _cargar_fuente(negrita=True, tamano=88)
        fuente_st = _cargar_fuente(negrita=True, tamano=52)
        fuente_st_etiqueta = _cargar_fuente(negrita=True, tamano=15)
        fuente_sensacion = _cargar_fuente(tamano=22)
        fuente_fila_etiqueta = _cargar_fuente(tamano=20)
        fuente_fila_valor = _cargar_fuente(negrita=True, tamano=24)
        # El viento va en 22 para que la dirección completa quepa
        fuente_viento = _cargar_fuente(negrita=True, tamano=22)
        fuente_tag = _cargar_fuente(negrita=True, tamano=24)

        for i, bloque in enumerate(bloques):
            x0 = margen + i * (ancho_panel + 18)
            x1 = x0 + ancho_panel
            xc = (x0 + x1) // 2

            # Foto de fondo según el clima (con esquinas redondeadas y
            # oscurecida para que el texto se lea); si no hay foto, el
            # panel queda con el color sólido de siempre
            ruta_fondo = seleccionar_fondo(bloque)
            if ruta_fondo:
                try:
                    foto = Image.open(ruta_fondo).convert("RGB")
                    foto = foto.resize((ancho_panel, alto_panel),
                                     Image.LANCZOS)
                    capa = Image.new("RGB", foto.size, COLOR_FONDO)
                    foto = Image.blend(foto, capa, 0.55)
                    mascara = Image.new("L", (ancho_panel, alto_panel), 0)
                    ImageDraw.Draw(mascara).rounded_rectangle(
                        [0, 0, ancho_panel, alto_panel], radius=18, fill=255)
                    img.paste(foto, (x0, y_panel), mascara)
                    draw = ImageDraw.Draw(img)
                except Exception as e:
                    logger.warning(f"No se pudo cargar el fondo: {e}")
                    ruta_fondo = None
            if not ruta_fondo:
                draw.rounded_rectangle([x0, y_panel, x1, y_panel + alto_panel],
                                       radius=18, fill=COLOR_PANEL)
            draw.rounded_rectangle([x0, y_panel, x1, y_panel + alto_panel],
                                   radius=18, outline=COLOR_BORDE_PANEL,
                                   width=2)

            y = y_panel + 18
            y = _texto_centrado(draw, xc, y, bloque['nombre'],
                                fuente_nombre, COLOR_TEXTO)
            y = _texto_centrado(draw, xc, y + 4, bloque['horas'],
                                fuente_horas, COLOR_TEXTO_SUAVE)

            # Glifo del clima (según código WMO dominante del bloque)
            glifo = GLIFOS_CLIMA.get(bloque.get('codigo'), "☁")
            y = _texto_centrado(draw, xc, y + 10, glifo,
                                fuente_glifo, COLOR_TEXTO_SUAVE)

            # Temperatura grande + sensación térmica (S.T.) a su lado,
            # ambas con color según su valor, como en MeteoAlert
            temp = bloque.get('temp_media')
            sensacion = bloque.get('sensacion_media')
            texto_temp = f"{temp:.0f}°" if temp is not None else "--°"
            texto_st = (f"{sensacion:.0f}°"
                        if sensacion is not None else "--°")
            bbox_temp = draw.textbbox((0, 0), texto_temp, font=fuente_temp)
            bbox_st = draw.textbbox((0, 0), texto_st, font=fuente_st)
            ancho_temp = bbox_temp[2] - bbox_temp[0]
            ancho_st = bbox_st[2] - bbox_st[0]
            ancho_grupo = ancho_temp + 26 + ancho_st
            x_temp = xc - ancho_grupo // 2
            x_st = x_temp + ancho_temp + 26
            y_temp = y + 6
            draw.text((x_temp, y_temp), texto_temp, font=fuente_temp,
                      fill=_color_temperatura(temp))
            # Etiqueta "SENSACIÓN TÉRMICA" sobre el número de S.T.
            draw.text((x_st, y_temp + 4), "SENSACIÓN",
                      font=fuente_st_etiqueta, fill=COLOR_TEXTO_SUAVE)
            draw.text((x_st, y_temp + 22), "TÉRMICA",
                      font=fuente_st_etiqueta, fill=COLOR_TEXTO_SUAVE)
            draw.text((x_st, y_temp + 40), texto_st, font=fuente_st,
                      fill=_color_temperatura(sensacion))
            y = max(y_temp + bbox_temp[3], y_temp + 40 + bbox_st[3]) + 12

            # Línea divisoria del panel
            y += 18
            draw.line([x0 + 20, y, x1 - 20, y], fill=COLOR_BORDE_PANEL, width=2)
            y += 16

            # Filas de datos: lluvia (con color según %), viento, presión.
            # Etiquetas en lenguaje sencillo y viento con la dirección
            # completa cuando cabe ("NORTE 17–21 km/h"); si no cabe, la
            # abreviatura ("N 17–21 km/h")
            filas = []
            prob = bloque.get('prob_max')
            filas.append(("LLUVIA",
                          f"{prob:.0f}%" if prob is not None else "--",
                          _color_lluvia(prob), fuente_fila_valor))
            direccion = bloque.get('viento_dir') or "--"
            direccion_corta = DIRECCION_CORTA.get(direccion, direccion)
            vmin = bloque.get('viento_min')
            vmax = bloque.get('viento_max')
            if vmin is not None and vmax is not None and vmin != vmax:
                rango = f"{vmin:.0f}–{vmax:.0f} km/h"
            elif vmax is not None:
                rango = f"{vmax:.0f} km/h"
            else:
                rango = ""
            texto_viento = f"{direccion} {rango}".strip()
            ancho_disponible = ancho_panel - 24 - 110
            if draw.textlength(texto_viento,
                               font=fuente_viento) > ancho_disponible:
                texto_viento = f"{direccion_corta} {rango}".strip()
            filas.append(("VIENTO", texto_viento, COLOR_TEXTO, fuente_viento))
            presion = bloque.get('presion_media')
            filas.append(("PRESIÓN",
                          f"{presion:.0f} hPa" if presion is not None else "--",
                          COLOR_TEXTO, fuente_fila_valor))

            for etiqueta, valor, color_valor, fuente_valor in filas:
                draw.text((x0 + 24, y), etiqueta,
                          font=fuente_fila_etiqueta, fill=COLOR_TEXTO_SUAVE)
                bbox = draw.textbbox((0, 0), valor, font=fuente_valor)
                draw.text((x1 - 24 - (bbox[2] - bbox[0]), y - 2), valor,
                          font=fuente_valor, fill=color_valor)
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

        # Contador discreto de la próxima festividad (solo en temporada)
        cuenta = texto_cuenta_regresiva()
        if cuenta:
            fuente_cuenta = _cargar_fuente(tamano=16)
            _texto_centrado(draw, ANCHO // 2, ALTO - 66,
                            f"•  {cuenta}  •",
                            fuente_cuenta, COLOR_TEXTO_SUAVE)

        img.save(ruta_salida, format="PNG")
        logger.info(f"✅ Tarjeta diaria generada: {ruta_salida}")
        return ruta_salida

    except Exception as e:
        logger.error(f"Error generando tarjeta diaria: {e}")
        import traceback
        traceback.print_exc()
        return None

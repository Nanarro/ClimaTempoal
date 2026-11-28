"""
Narrador con Gemini (API gratuita de Google AI Studio) y respaldo
con Groq (API gratuita, sin tarjeta).

Escribe las partes narradas del reporte: el panorama semanal
("LA SEMANA EN TEMPOAL"), la actualización del día, la lectura de
la gráfica de frío de Navidad y la explicación de las alertas en
palabras simples. Todo es opcional y best-effort: sin llave, sin red
o si la respuesta no pasa la validación, el reporte sigue igual sin
esa parte (nunca tumba el reporte ni el envío).

La llave de Gemini (GEMINI_API_KEY) se guarda como secreto de
GitHub; sin tarjeta no hay manera de que genere un cobro. El
respaldo es Groq (GROQ_API_KEY, también secreto, también gratis y
sin tarjeta): si Gemini no responde por saturación o cuota, se
intenta una vez con Groq (modelo openai/gpt-oss-120b). El modelo
solo recibe los números del pronóstico que ya baja Open-Meteo (más
el resumen del ensemble); no recibe datos personales ni secretos.
"""

import os
import re
import time
import unicodedata
from datetime import datetime, timedelta

import requests

from .grafica_navidad import frase_rango_minima
from .utils import logger, DIAS_ESP, obtener_hora_mexico

# Gemini 3.5 Flash-Lite: capa gratuita de Google AI Studio (sin
# tarjeta; el bot hace hasta 4 llamadas al día, una por sección
# narrada). Antes el principal era gemini-3.8-flash, pero en todas
# las corridas en vivo falló por saturación (503) o por cuota (429)
# y siempre respondió el ligero, así que el ligero es ahora el
# principal y 3.8 Flash sale de la cadena. El 2.5 Flash quedó fuera
# antes: Google lo limitó a quienes ya lo usaban (HTTP 404 con
# llaves nuevas).
MODELO_GEMINI = "gemini-3.5-flash-lite"
URL_GEMINI = ("https://generativelanguage.googleapis.com/v1beta/models/"
              "{modelo}:generateContent")

# Respaldo: Groq (plan gratuito, sin tarjeta), API compatible con
# OpenAI. Si Gemini no responde, se intenta una vez con
# openai/gpt-oss-120b (el modelo gratuito insignia de Groq;
# llama-3.3-70b-versatile salió del plan gratuito el 2026-08-16,
# no usarlo). Límites gratuitos: 30 RPM, 1.000 peticiones/día,
# 8.000 TPM; el bot hace 4 llamadas al día.
MODELO_GROQ = "openai/gpt-oss-120b"
URL_GROQ = "https://api.groq.com/openai/v1/chat/completions"

# Límites de la validación: la sección es corta (3-4 líneas).
MAX_LINEAS_NARRATIVA = 5
MAX_CARACTERES_NARRATIVA = 700

# Meses en español para reconocer fechas "N de <mes>" en la narrativa.
_MESES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5,
    "junio": 6, "julio": 7, "agosto": 8, "septiembre": 9,
    "setiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12,
}
_PATRON_FECHA = re.compile(
    r"(\d{1,2})\s+de\s+(" + "|".join(_MESES) + r")")
_PATRON_ANO = re.compile(r"20\d\d")

# Etiqueta corta del código WMO para el prompt (lo que ve el modelo).
_ETIQUETAS_CODIGO = {
    0: "despejado", 1: "mayormente despejado",
    2: "parcialmente nublado", 3: "nublado",
    45: "niebla", 48: "niebla",
    51: "llovizna", 53: "llovizna", 55: "llovizna",
    61: "lluvia ligera", 63: "lluvia", 65: "lluvia intensa",
    71: "nieve", 73: "nieve", 75: "nieve",
    80: "chubascos", 81: "chubascos", 82: "chubascos fuertes",
    95: "tormenta", 96: "tormenta con granizo",
    99: "tormenta con granizo",
}


def _sin_acentos(texto):
    """Quita acentos para comparar variantes (récord/record)."""
    descompuesto = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in descompuesto
                   if not unicodedata.combining(c))


def _etiqueta_codigo(codigo):
    """Palabra corta del código WMO (o 'variable' si no se conoce)."""
    try:
        return _ETIQUETAS_CODIGO.get(int(codigo), "variable")
    except (TypeError, ValueError):
        return "variable"


def _num(valor, defecto=0):
    """Número o el defecto si falta / no es número."""
    try:
        return float(valor)
    except (TypeError, ValueError):
        return defecto


def construir_prompt(daily, ensemble_resumen=None):
    """
    Arma el prompt para Gemini (pura): los 7 días del pronóstico
    en forma compacta + las instrucciones de redacción.

    `daily` es el dict `daily` de Open-Meteo. `ensemble_resumen` es
    el dict de resumen_ensemble_hoy (opcional).
    """
    daily = daily or {}
    tiempos = daily.get('time') or []
    tmax = daily.get('temperature_2m_max') or []
    tmin = daily.get('temperature_2m_min') or []
    lluvias = daily.get('precipitation_sum') or []
    probs = daily.get('precipitation_probability_max') or []
    codigos = daily.get('weather_code') or []

    lineas = ["Datos del pronóstico de 7 días para Tempoal, Veracruz "
              "(Open-Meteo, modelos GFS/ECMWF):"]
    for i, fecha in enumerate(tiempos[:7]):
        try:
            dt = datetime.strptime(fecha, "%Y-%m-%d")
            dia = DIAS_ESP.get(dt.strftime("%A"), "DÍA")
            fecha_corta = dt.strftime("%d/%m")
        except (ValueError, TypeError):
            dia, fecha_corta = "DÍA", str(fecha)
        lineas.append(
            f"- {dia} {fecha_corta}: mín {round(_num(tmin[i] if i < len(tmin) else 0))}°"
            f" – máx {round(_num(tmax[i] if i < len(tmax) else 0))}°C,"
            f" lluvia {round(_num(lluvias[i] if i < len(lluvias) else 0), 1)} mm,"
            f" prob. lluvia {round(_num(probs[i] if i < len(probs) else 0))}%,"
            f" {_etiqueta_codigo(codigos[i] if i < len(codigos) else None)}")

    if ensemble_resumen:
        probs_bloque = ensemble_resumen.get('prob_lluvia') or {}
        partes = []
        for nombre in ("POR LA MAÑANA", "TARDE", "NOCHE"):
            p = probs_bloque.get(nombre)
            if p is not None:
                partes.append(f"{nombre.lower()} {round(_num(p))}%")
        confianza = ensemble_resumen.get('confianza')
        if partes or confianza:
            detalle = ", ".join(partes)
            lineas.append("Hoy (ensemble ECMWF, probabilidad real de "
                          f"lluvia: {detalle or 'sin datos'}"
                          + (f"; confianza {confianza}"
                             if confianza else "") + ").")

    lineas.append("")
    lineas.append(
        "Eres el meteorólogo de Protección Civil de Tempoal. Escribe "
        "3 o 4 líneas cortas en español, con tono serio y amigable, "
        "como un pronóstico narrado de la semana. Usa SOLO los datos "
        "de arriba: no inventes fechas, frentes con nombre, ni "
        "récords. Si un fenómeno no aparece en los datos de arriba, "
        "no lo menciones. Si un día no tiene nada notable, no lo "
        "menciones. No saludes ni te presentes, solo el panorama.")
    return "\n".join(lineas)


def validar_narrativa(texto, fechas_ventana):
    """
    Valida la narrativa de Gemini (pura): True si se puede publicar.

    Reglas: texto no vacío; 1 a 5 líneas; 700 caracteres máximo;
    sin años (20XX); sin "récord" ni "históric" en ninguna variante;
    sin fechas "N de <mes>" fuera de la ventana de 7 días
    (`fechas_ventana` es la lista de `daily['time']`, YYYY-MM-DD).
    Si una fecha no se puede verificar, se rechaza.
    """
    try:
        if not texto or not str(texto).strip():
            return False
        texto = str(texto).strip()
        lineas = [l for l in texto.splitlines() if l.strip()]
        if not 1 <= len(lineas) <= MAX_LINEAS_NARRATIVA:
            return False
        if len(texto) > MAX_CARACTERES_NARRATIVA:
            return False
        normalizado = _sin_acentos(texto.lower())
        if _PATRON_ANO.search(normalizado):
            return False
        if "record" in normalizado or "historic" in normalizado:
            return False
        ventana = set()
        for fecha in (fechas_ventana or []):
            try:
                dt = datetime.strptime(fecha, "%Y-%m-%d")
                ventana.add((dt.day, dt.month))
            except (ValueError, TypeError):
                continue
        for coincidencia in _PATRON_FECHA.finditer(normalizado):
            dia = int(coincidencia.group(1))
            mes = _MESES[coincidencia.group(2)]
            if (dia, mes) not in ventana:
                return False
        return True
    except Exception:
        return False


def resumen_ensemble_hoy(bloques):
    """
    Resumen del ensemble de hoy para el prompt (pura).

    Recibe el resultado de `obtener_bloques_diarios` (lista de 3
    bloques) y devuelve {'prob_lluvia': {nombre: %}, 'confianza': ...}
    con la probabilidad real de lluvia por bloque y la confianza
    (ALTA/MEDIA/BAJA). Sin datos, devuelve un dict vacío.
    """
    try:
        if not bloques:
            return {}
        probs = {}
        for bloque in bloques:
            nombre = (bloque.get('nombre') or '').upper()
            if not nombre:
                continue
            prob = bloque.get('prob_lluvia_ens')
            if prob is None:
                prob = bloque.get('prob_max')
            if prob is not None:
                probs[nombre] = round(_num(prob))
        confianza = None
        try:
            from .formato import nivel_confianza
            confianza = nivel_confianza(bloques)[0]
        except Exception:
            confianza = None
        resumen = {'prob_lluvia': probs}
        if confianza:
            resumen['confianza'] = confianza
        return resumen
    except Exception:
        return {}


def _resumen_ensemble_crudo(daily, ensemble):
    """Resumen de hoy a partir del dict crudo del ensemble ECMWF."""
    from .formato import extraer_ensemble_bloque
    hoy = ((daily or {}).get('time') or [None])[0]
    bloques = []
    for nombre, inicio, fin in (("POR LA MAÑANA", 6, 12),
                                ("TARDE", 12, 18),
                                ("NOCHE", 18, 24)):
        ens = extraer_ensemble_bloque(ensemble, inicio, fin, hoy)
        if ens:
            bloques.append({
                'nombre': nombre,
                'temp_spread': ens.get('temp_spread'),
                'prob_lluvia_ens': ens.get('prob_lluvia_ens'),
            })
    if not bloques:
        return None
    resumen = resumen_ensemble_hoy(bloques)
    return resumen or None


def _extraer_texto_gemini(data):
    """Saca el texto de candidates[0].content.parts[0].text (o None)."""
    try:
        candidatos = (data or {}).get('candidates') or []
        if not candidatos:
            return None
        partes = (candidatos[0].get('content') or {}).get('parts') or []
        textos = [p.get('text') for p in partes
                  if isinstance(p, dict) and p.get('text')]
        texto = "\n".join(textos).strip()
        return texto or None
    except Exception:
        return None


def _extraer_texto_groq(data):
    """Saca el texto de choices[0].message.content (o None)."""
    try:
        opciones = (data or {}).get('choices') or []
        if not opciones:
            return None
        mensaje = (opciones[0].get('message') or {})
        texto = (mensaje.get('content') or "").strip()
        return texto or None
    except Exception:
        return None


def llamar_groq(prompt, api_key, modelo=MODELO_GROQ, etiqueta="Groq"):
    """
    Una llamada a Groq (best-effort, nunca lanza excepciones).

    Devuelve el texto crudo de la respuesta o None. Sin llave no hay
    llamada de red. Un solo intento, tiempo límite 20 s. La llave
    viaja en el header Authorization: Bearer (el patrón de la API
    compatible con OpenAI) y nunca se registra en el log.
    """
    try:
        llave = (api_key or "").strip()
        if not llave:
            return None
        headers = {"Content-Type": "application/json",
                   "Authorization": "Bearer " + llave}
        cuerpo = {
            "model": modelo,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.5,
            "max_tokens": 1024,
        }
        logger.info(f"🤖 {etiqueta}: pidiendo a Groq ({modelo})...")
        respuesta = requests.post(URL_GROQ, headers=headers, json=cuerpo,
                                  timeout=20)
        respuesta.raise_for_status()
        texto = _extraer_texto_groq(respuesta.json())
        if not texto:
            logger.warning(f"🤖 {etiqueta}: Groq respondió sin texto")
            return None
        return texto.strip()
    except requests.HTTPError as e:
        codigo = (e.response.status_code
                  if e.response is not None else "?")
        mensaje = ""
        try:
            mensaje = (e.response.json()
                       .get("error", {}).get("message", ""))
        except Exception:
            mensaje = ""
        logger.warning(f"🤖 {etiqueta}: Groq error HTTP {codigo} "
                       f"({mensaje[:200]}), se omite")
        return None
    except requests.Timeout:
        logger.warning(f"🤖 {etiqueta}: timeout con Groq")
        return None
    except requests.RequestException as e:
        logger.warning(f"🤖 {etiqueta}: error de red con Groq ({e})")
        return None
    except Exception as e:
        logger.warning(f"🤖 {etiqueta}: error inesperado con Groq ({e})")
        return None


def llamar_gemini(prompt, api_key, modelo=MODELO_GEMINI,
                  etiqueta="Gemini", groq_api_key=None):
    """
    Una llamada a Gemini (best-effort, nunca lanza excepciones).

    Devuelve el texto crudo de la respuesta o None. Sin llave no hay
    llamada de red. Primero se intenta el modelo dado (2 intentos);
    si no responde por transporte, se intenta una vez con Groq
    (respaldo, solo si hay llave GROQ_API_KEY); sin llave Groq el
    respaldo se omite y se devuelve None. Por intento, el tiempo
    límite es 20 s. La llave viaja como parámetro ?key= en la URL
    (el patrón REST documentado de Google; las llaves nuevas con
    prefijo "AQ." dan 404 si van en el header x-goog-api-key) y
    nunca se registra en el log: la URL no se registra.
    """
    try:
        llave = (api_key or "").strip()
        if not llave:
            return None
        texto = _llamar_modelo(prompt, llave, modelo, etiqueta, 2)
        if texto:
            return texto
        llave_groq = (groq_api_key or "").strip()
        if not llave_groq:
            logger.warning(f"🤖 {etiqueta}: sin llave GROQ_API_KEY, "
                           "el respaldo se omite")
            return None
        texto = llamar_groq(prompt, llave_groq, etiqueta=etiqueta)
        if texto:
            logger.info(f"🤖 {etiqueta}: respondió Groq (respaldo)")
            return texto
        return None
    except Exception as e:
        logger.warning(f"🤖 {etiqueta}: error inesperado ({e})")
        return None


def _llamar_modelo(prompt, llave, modelo, etiqueta, intentos):
    """
    Intenta una llamada a un modelo concreto (best-effort).

    Reintenta el timeout, el error de red y los errores HTTP
    transitorios (429 y 5xx, con 10 s de espera, porque Google mismo
    pide reintentarlos); los demás errores HTTP (400/401/403/404) son
    terminales. Devuelve el texto o None. Nunca registra la llave.
    """
    url = URL_GEMINI.format(modelo=modelo) + "?key=" + llave
    headers = {"Content-Type": "application/json"}
    cuerpo = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.3,
                             "maxOutputTokens": 300},
    }
    for intento in range(1, intentos + 1):
        try:
            logger.info(f"🤖 {etiqueta}: pidiendo a Gemini "
                        f"({modelo}, intento {intento}/{intentos})...")
            respuesta = requests.post(url, headers=headers, json=cuerpo,
                                      timeout=20)
            respuesta.raise_for_status()
            texto = _extraer_texto_gemini(respuesta.json())
            if not texto:
                logger.warning(f"🤖 {etiqueta}: Gemini respondió "
                               "sin texto")
                return None
            return texto.strip()
        except requests.Timeout:
            logger.warning(f"🤖 {etiqueta}: timeout en intento "
                           f"{intento}/{intentos} ({modelo})")
        except requests.HTTPError as e:
            codigo = (e.response.status_code
                      if e.response is not None else "?")
            # El cuerpo del error dice el porqué (p. ej. el modelo
            # no existe para esta llave); se registra recortado
            # para que el próximo fallo se diagnostique solo.
            # El cuerpo nunca contiene la llave.
            mensaje = ""
            try:
                mensaje = (e.response.json()
                           .get("error", {}).get("message", ""))
            except Exception:
                mensaje = ""
            # 429 y 5xx son transitorios (Google mismo pide
            # reintentarlos): se reintenta una vez tras 10 s.
            # 400/401/403/404 son de configuración: no se reintenta.
            if codigo in (429, 500, 502, 503, 504) and intento < intentos:
                logger.warning(f"🤖 {etiqueta}: error HTTP "
                               f"{codigo} ({mensaje[:200]}), "
                               f"reintentando...")
                time.sleep(10)
                continue
            logger.warning(f"🤖 {etiqueta}: error HTTP "
                           f"{codigo} ({mensaje[:200]}), se omite")
            return None
        except requests.RequestException as e:
            logger.warning(f"🤖 {etiqueta}: error de red ({e})")
        except Exception as e:
            logger.warning(f"🤖 {etiqueta}: error inesperado ({e})")
            return None
        if intento < intentos:
            time.sleep(2)
    logger.warning(f"🤖 {etiqueta}: sin respuesta tras {intentos} "
                   f"intentos ({modelo})")
    return None


def obtener_narrativa_semanal(daily, ensemble=None, api_key=None,
                              modelo=MODELO_GEMINI, groq_api_key=None):
    """
    Pide a Gemini la narrativa semanal (best-effort, nunca lanza
    excepciones). Devuelve el texto validado o None.

    La llave se toma del argumento o de GEMINI_API_KEY; sin llave no
    hay llamada de red. Si Gemini falla por transporte, se intenta
    una vez con Groq (`groq_api_key` o GROQ_API_KEY). Si la llamada
    falla, la respuesta viene vacía o el texto no pasa la
    validación, devuelve None y el reporte sigue sin la sección. La
    llave nunca se registra en el log.
    """
    try:
        llave = (api_key or os.environ.get("GEMINI_API_KEY") or "").strip()
        if not llave:
            logger.info("🤖 Narrador: sin llave GEMINI_API_KEY, "
                        "se omite la sección semanal")
            return None
        llave_groq = (groq_api_key
                      or os.environ.get("GROQ_API_KEY") or "").strip()
        if not (daily or {}).get('time'):
            logger.warning("🤖 Narrador: sin datos diarios, se omite")
            return None

        ensemble_resumen = None
        if ensemble is not None:
            try:
                ensemble_resumen = _resumen_ensemble_crudo(daily, ensemble)
            except Exception as e:
                logger.warning("🤖 Narrador: sin resumen de ensemble "
                               f"({e})")

        prompt = construir_prompt(daily, ensemble_resumen)
        texto = llamar_gemini(prompt, llave, modelo, etiqueta="Narrador",
                              groq_api_key=llave_groq)
        if not texto:
            logger.warning("🤖 Narrador: sin texto de Gemini, se omite")
            return None
        fechas = (daily or {}).get('time') or []
        if validar_narrativa(texto, fechas):
            logger.info("✅ Narrador: narrativa semanal lista")
            return texto.strip()
        logger.warning("🤖 Narrador: la narrativa no pasó la "
                       "validación, se omite")
        return None
    except Exception as e:
        logger.warning(f"🤖 Narrador: error inesperado ({e})")
        return None

# ---------------------------------------------------------------------------
# Narrativa del día: la "actualización" del reporte
# ---------------------------------------------------------------------------

def _fecha_larga(fecha_iso):
    """'viernes 27 de noviembre' a partir de 'YYYY-MM-DD' (sin año)."""
    try:
        dt = datetime.strptime(fecha_iso, "%Y-%m-%d")
        meses = ("", "enero", "febrero", "marzo", "abril", "mayo", "junio",
                 "julio", "agosto", "septiembre", "octubre", "noviembre",
                 "diciembre")
        return (f"{DIAS_ESP.get(dt.strftime('%A'), 'Día').lower()} "
                f"{dt.day} de {meses[dt.month]}")
    except (ValueError, TypeError):
        return str(fecha_iso)


def _hora_corta(valor_iso):
    """'06:52' a partir de 'YYYY-MM-DDTHH:MM' (o '' si no se puede)."""
    try:
        return datetime.fromisoformat(valor_iso).strftime("%H:%M")
    except (ValueError, TypeError):
        return ""


def _viento_dominante_dia(bloques):
    """
    Dirección de viento dominante del día a partir de los bloques.

    La más frecuente entre los 3 bloques; si no hay mayoría (cada
    bloque sopla de un lado distinto) devuelve "variable". Pura.
    """
    dirs = [b.get('viento_dir') for b in (bloques or [])
            if b.get('viento_dir')]
    if not dirs:
        return None
    conteo = {}
    for d in dirs:
        conteo[d] = conteo.get(d, 0) + 1
    mas_frecuente = max(conteo.values())
    ganadoras = [d for d, c in conteo.items() if c == mas_frecuente]
    if len(ganadoras) == 1:
        return ganadoras[0]
    return "variable"


def construir_prompt_dia(datos, ensemble=None):
    """
    Arma el prompt de la narrativa del día (pura): condiciones
    actuales, los 3 bloques con su probabilidad real de lluvia,
    resumen de las 24 horas, tendencia de presión y sol.

    `datos` es el dict completo de Open-Meteo (current + hourly +
    daily). Con `ensemble`, las probabilidades de lluvia de los
    bloques son las reales del ensemble ECMWF.
    """
    from .formato import nivel_confianza, obtener_bloques_diarios
    from .interpretador import frase_lluvia

    datos = datos or {}
    daily = datos.get('daily') or {}
    hourly = datos.get('hourly') or {}
    current = datos.get('current') or {}
    hoy = (daily.get('time') or [None])[0]

    lineas = [f"Datos de HOY, {_fecha_larga(hoy)}, en Tempoal, "
              "Veracruz (Open-Meteo, modelos GFS/ECMWF):"]

    temp_ahora = _num(current.get('temperature_2m'), None)
    sens_ahora = _num(current.get('apparent_temperature'), None)
    humedad = current.get('relative_humidity_2m')
    viento_ahora = current.get('wind_speed_10m')
    codigo_ahora = _etiqueta_codigo(current.get('weather_code'))
    partes_ahora = []
    if temp_ahora is not None:
        partes_ahora.append(f"{round(temp_ahora, 1)} °C")
    if sens_ahora is not None:
        partes_ahora.append(f"sensación {round(sens_ahora, 1)} °C")
    if humedad is not None:
        partes_ahora.append(f"humedad {round(_num(humedad))}%")
    if viento_ahora is not None:
        partes_ahora.append(f"viento {round(_num(viento_ahora), 1)} km/h")
    partes_ahora.append(codigo_ahora)
    lineas.append("- Ahora: " + ", ".join(partes_ahora) + ".")

    try:
        bloques = obtener_bloques_diarios(datos, ensemble=ensemble)
    except Exception:
        bloques = []
    for bloque in bloques:
        nombre = (bloque.get('nombre') or '').upper()
        prob = bloque.get('prob_max')
        temp_media = bloque.get('temp_media')
        sens_media = bloque.get('sensacion_media')
        viento_dir = bloque.get('viento_dir') or "variable"
        v_min = bloque.get('viento_min')
        v_max = bloque.get('viento_max')
        presion = bloque.get('presion_media')
        etiqueta = _etiqueta_codigo(bloque.get('codigo'))
        partes = []
        if prob is not None:
            partes.append(
                f"lluvia {round(_num(prob))}%"
                + (" (ensemble ECMWF)" if ensemble is not None else ""))
        if temp_media is not None:
            partes.append(f"{round(_num(temp_media), 1)} °C de media")
        if (sens_media is not None and temp_media is not None
                and abs(_num(sens_media) - _num(temp_media)) >= 3):
            partes.append(f"se sentirá de {round(_num(sens_media), 1)} °C")
        if v_min is not None and v_max is not None:
            partes.append(
                f"viento {viento_dir.lower()} "
                f"{round(_num(v_min))}–{round(_num(v_max))} km/h")
        if presion is not None:
            partes.append(f"presión {round(_num(presion))} hPa")
        partes.append(etiqueta)
        # La intensidad de lluvia es la misma que dice la tarjeta:
        # frase_lluvia usa la probabilidad de lluvia FUERTE del
        # ensemble, que el prompt no incluía y por eso la narrativa
        # decía "lluvia ligera" donde la tarjeta decía "chubascos
        # fuertes". Al darle la frase exacta, ambas dicen lo mismo.
        try:
            frase_tarjeta = frase_lluvia(bloque)
        except Exception:
            frase_tarjeta = None
        if frase_tarjeta:
            partes.append(f"la tarjeta dice: «{frase_tarjeta}»")
        lineas.append(f"- {nombre} ({bloque.get('horas', '')}): "
                      + ", ".join(partes) + ".")

    temps_24 = [t for t in (hourly.get('temperature_2m') or [])[:24]
                if t is not None]
    probs_24 = [p for p in
                (hourly.get('precipitation_probability') or [])[:24]
                if p is not None]
    rafagas_24 = [r for r in (hourly.get('wind_gusts_10m') or [])[:24]
                  if r is not None]
    presiones_24 = [p for p in (hourly.get('surface_pressure') or [])[:24]
                    if p is not None]
    resumen_24 = []
    if temps_24:
        resumen_24.append(
            f"mínima {round(min(temps_24), 1)} °C, "
            f"máxima {round(max(temps_24), 1)} °C")
    if probs_24:
        resumen_24.append(
            f"prob. máxima de lluvia {round(max(probs_24))}%")
    if rafagas_24:
        resumen_24.append(f"ráfaga máxima {round(max(rafagas_24))} km/h")
    if resumen_24:
        lineas.append("- En 24 h: " + ", ".join(resumen_24) + ".")
    # Viento del día en una sola dirección: la dominante entre los
    # bloques, o "variable" si cada bloque sopla de un lado. Así la
    # narrativa no junta dos direcciones opuestas en una frase ni
    # mezcla la velocidad sostenida con las ráfagas en un número.
    viento_dia = _viento_dominante_dia(bloques)
    if viento_dia:
        sostenido = (max((b.get('viento_max') or 0) for b in bloques)
                     if bloques else 0)
        rafaga = round(max(rafagas_24)) if rafagas_24 else None
        linea_viento = f"- Viento del día: {viento_dia.lower()}"
        if sostenido:
            linea_viento += f", sostenido máx. {round(sostenido)} km/h"
        if rafaga is not None:
            linea_viento += f", ráfagas hasta {rafaga} km/h"
        lineas.append(linea_viento + ".")
    if len(presiones_24) >= 2:
        delta = round(presiones_24[-1] - presiones_24[0], 1)
        sentido = ("baja" if delta < 0 else
                   "sube" if delta > 0 else "se mantiene")
        lineas.append(
            f"- Presión: de {round(presiones_24[0])} hPa a "
            f"{round(presiones_24[-1])} hPa ({sentido} "
            f"{abs(delta)} hPa en el día).")

    amanecer = _hora_corta((daily.get('sunrise') or [None])[0])
    atardecer = _hora_corta((daily.get('sunset') or [None])[0])
    if amanecer or atardecer:
        lineas.append(f"- Amanecer {amanecer or 's/d'} | "
                      f"Atardecer {atardecer or 's/d'}.")
    try:
        confianza = nivel_confianza(bloques)[0] if bloques else None
    except Exception:
        confianza = None
    if confianza:
        lineas.append(f"- Confianza del pronóstico: {confianza}.")

    lineas.append("")
    lineas.append(
        "Eres el meteorólogo de Protección Civil de Tempoal. Escribe "
        "UN párrafo corto (3 a 5 líneas, unas 500 caracteres) en "
        "español, con tono serio y amigable, como la actualización "
        "del día de un meteorólogo: cuenta qué está pasando, cuándo "
        "llueve más fuerte o más leve, y qué significan el viento y "
        "la presión. Usa SOLO los datos de arriba: no inventes "
        "fechas, frentes con nombre, ni récords, y no escribas años. "
        "Si un fenómeno no aparece en los datos, no lo menciones. "
        "La intensidad de lluvia de cada bloque es la que dice la "
        "tarjeta en los datos: si dice chubascos fuertes, no digas "
        "lluvia ligera, y al revés. Del viento habla con una sola "
        "dirección (la dominante del día) o di 'variable' si cambia: "
        "no juntes dos direcciones en una frase, y no mezcles la "
        "velocidad sostenida con las ráfagas en un solo número. "
        "No saludes ni te presentes, solo la actualización.")
    return "\n".join(lineas)


def obtener_narrativa_dia(datos, ensemble=None, api_key=None,
                          modelo=MODELO_GEMINI, groq_api_key=None):
    """
    Pide a Gemini la narrativa del día (best-effort, nunca lanza
    excepciones). Devuelve el párrafo validado o None.

    La llave se toma del argumento o de GEMINI_API_KEY; sin llave no
    hay llamada de red. Si Gemini falla por transporte, se intenta
    una vez con Groq (`groq_api_key` o GROQ_API_KEY). La ventana de
    validación es solo la fecha de hoy: el párrafo no debe mencionar
    otras fechas.
    """
    try:
        llave = (api_key or os.environ.get("GEMINI_API_KEY") or "").strip()
        if not llave:
            logger.info("🤖 Narrativa del día: sin llave GEMINI_API_KEY, "
                        "se omite")
            return None
        llave_groq = (groq_api_key
                      or os.environ.get("GROQ_API_KEY") or "").strip()
        daily = (datos or {}).get('daily') or {}
        if not daily.get('time'):
            logger.warning("🤖 Narrativa del día: sin datos diarios, "
                           "se omite")
            return None
        prompt = construir_prompt_dia(datos, ensemble=ensemble)
        texto = llamar_gemini(prompt, llave, modelo,
                              etiqueta="Narrativa del día",
                              groq_api_key=llave_groq)
        if not texto:
            logger.warning("🤖 Narrativa del día: sin texto de Gemini, "
                           "se omite")
            return None
        if validar_narrativa(texto, [daily['time'][0]]):
            logger.info("✅ Narrativa del día lista")
            return texto.strip()
        logger.warning("🤖 Narrativa del día: el texto no pasó la "
                       "validación, se omite")
        return None
    except Exception as e:
        logger.warning(f"🤖 Narrativa del día: error inesperado ({e})")
        return None


# ---------------------------------------------------------------------------
# Interpretación de la gráfica de frío de Navidad
# ---------------------------------------------------------------------------

def construir_prompt_navidad(distribucion):
    """
    Arma el prompt para leer la gráfica de Navidad (pura).

    `distribucion` es el dict de distribucion_minima_navidad: la
    distribución de la mínima del 25 de diciembre por rango, el
    rango más probable, P(<12), P(<10) y la probabilidad de lluvia
    esa noche (si hay dato). El prompt lleva la distribución
    completa más los datos clave ya calculados.
    """
    dist = distribucion or {}
    pares = dist.get('distribucion') or []
    if not pares:
        return ""

    lineas = ["Distribución de la mínima para la noche del 24 al 25 "
              "de diciembre en Tempoal, según el ensemble GFS "
              "(31 miembros):"]
    for etiqueta, pct in pares:
        lineas.append(f"- {etiqueta}: {pct}%")
    mas_probable = dist.get('mas_probable')
    if mas_probable:
        etiqueta, pct = mas_probable
        lineas.append(
            f"Lo más probable: {frase_rango_minima(etiqueta)} ({pct}%).")
    if dist.get('prob_frio') is not None:
        lineas.append(
            f"Frío (<12 °C): {dist.get('prob_frio')}%. "
            f"Muy frío (<10 °C): {dist.get('prob_muy_frio', 0)}%.")
    if dist.get('prob_lluvia') is not None:
        lineas.append(
            f"Probabilidad de lluvia esa noche: {dist['prob_lluvia']}%.")
    lineas.append("")
    lineas.append(
        "Eres el meteorólogo de Protección Civil de Tempoal. Escribe "
        "1 o 2 líneas cortas en español, con tono serio y amigable, "
        "leyendo esta distribución: dónde se concentra el frío, cuál "
        "es la mínima más probable, si el 25 de diciembre en sí pinta "
        "frío o no, y si lloverá esa noche. Usa SOLO los números de "
        "arriba: no inventes fechas fuera del 24 al 26 de diciembre, "
        "ni récords, y no escribas años. No saludes ni te presentes, "
        "solo la lectura.")
    return "\n".join(lineas)


def obtener_interpretacion_navidad(datos_navidad, api_key=None,
                                   modelo=MODELO_GEMINI,
                                   groq_api_key=None):
    """
    Pide a Gemini la lectura de la gráfica de Navidad (best-effort,
    nunca lanza excepciones). Devuelve 1-2 líneas validadas o None.

    `datos_navidad` es el dict de distribucion_minima_navidad. La
    ventana de validación son el 25 de diciembre y los días cercanos
    (24 y 26). Si Gemini falla por transporte, se intenta una vez
    con Groq (`groq_api_key` o GROQ_API_KEY). Sin datos, sin llave
    o si la respuesta no pasa la validación, devuelve None.
    """
    try:
        dist = datos_navidad or {}
        if not dist.get('distribucion'):
            logger.info("🤖 Navidad: sin datos de distribución, se omite")
            return None
        llave = (api_key or os.environ.get("GEMINI_API_KEY") or "").strip()
        if not llave:
            logger.info("🤖 Navidad: sin llave GEMINI_API_KEY, se omite")
            return None
        llave_groq = (groq_api_key
                      or os.environ.get("GROQ_API_KEY") or "").strip()
        prompt = construir_prompt_navidad(dist)
        texto = llamar_gemini(prompt, llave, modelo, etiqueta="Navidad",
                              groq_api_key=llave_groq)
        if not texto:
            logger.warning("🤖 Navidad: sin texto de Gemini, se omite")
            return None
        fechas = []
        fecha_25 = dist.get('fecha')
        if fecha_25 is not None:
            for delta in (-1, 0, 1):
                try:
                    fechas.append(
                        (fecha_25 + timedelta(days=delta)).isoformat())
                except (AttributeError, TypeError):
                    continue
        if validar_narrativa(texto, fechas):
            logger.info("✅ Navidad: interpretación lista")
            return texto.strip()
        logger.warning("🤖 Navidad: el texto no pasó la validación, "
                       "se omite")
        return None
    except Exception as e:
        logger.warning(f"🤖 Navidad: error inesperado ({e})")
        return None


# ---------------------------------------------------------------------------
# Explicación de las alertas en palabras simples
# ---------------------------------------------------------------------------

_PATRON_ETIQUETA_HTML = re.compile(r"<[^>]*>")


def _limpiar_alerta(alerta):
    """Quita las etiquetas HTML de una alerta y compacta espacios."""
    texto = _PATRON_ETIQUETA_HTML.sub("", str(alerta or ""))
    return " ".join(texto.split())


def construir_prompt_alertas(alertas):
    """
    Arma el prompt para explicar las alertas (pura).

    `alertas` es la lista de strings que ya construye main.py
    (títulos con fecha y datos). El prompt las lleva limpias de
    HTML, una por línea.
    """
    alertas = [a for a in (alertas or []) if str(a or "").strip()]
    lineas = ["Alertas meteorológicas vigentes para Tempoal:"]
    for alerta in alertas:
        lineas.append(f"- {_limpiar_alerta(alerta)}")
    lineas.append("")
    lineas.append(
        "Eres el meteorólogo de Protección Civil de Tempoal. Explica "
        "cada alerta en 1 o 2 líneas cortas en español, en palabras "
        "simples: qué significa y qué hacer. Usa SOLO la información "
        "de las alertas de arriba: no inventes nada más. No saludes "
        "ni te presentes, solo la explicación.")
    return "\n".join(lineas)


def obtener_explicacion_alertas(alertas, api_key=None, modelo=MODELO_GEMINI,
                                fechas_ventana=None, groq_api_key=None):
    """
    Pide a Gemini la explicación de las alertas (best-effort, nunca
    lanza excepciones). Devuelve el texto validado o None.

    Sin alertas o sin llave no hay llamada de red. Si Gemini falla
    por transporte, se intenta una vez con Groq (`groq_api_key` o
    GROQ_API_KEY). La ventana de validación son las fechas de los
    próximos 7 días (por defecto, desde hoy en hora de México); se
    puede pasar explícita (`fechas_ventana`, lista YYYY-MM-DD) para
    probar sin depender de la fecha actual.
    """
    try:
        alertas = [a for a in (alertas or []) if str(a or "").strip()]
        if not alertas:
            logger.info("🤖 Alertas: no hay alertas que explicar")
            return None
        llave = (api_key or os.environ.get("GEMINI_API_KEY") or "").strip()
        if not llave:
            logger.info("🤖 Alertas: sin llave GEMINI_API_KEY, se omite")
            return None
        llave_groq = (groq_api_key
                      or os.environ.get("GROQ_API_KEY") or "").strip()
        if fechas_ventana is None:
            hoy = obtener_hora_mexico().date()
            fechas_ventana = [(hoy + timedelta(days=i)).isoformat()
                              for i in range(7)]
        prompt = construir_prompt_alertas(alertas)
        texto = llamar_gemini(prompt, llave, modelo, etiqueta="Alertas",
                              groq_api_key=llave_groq)
        if not texto:
            logger.warning("🤖 Alertas: sin texto de Gemini, se omite")
            return None
        if validar_narrativa(texto, fechas_ventana):
            logger.info("✅ Alertas: explicación lista")
            return texto.strip()
        logger.warning("🤖 Alertas: el texto no pasó la validación, "
                       "se omite")
        return None
    except Exception as e:
        logger.warning(f"🤖 Alertas: error inesperado ({e})")
        return None

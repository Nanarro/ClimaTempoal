"""
Narrador semanal con Gemini (API gratuita de Google AI Studio).

Escribe la sección "LA SEMANA EN TEMPOAL" del reporte: un panorama
narrado de 3 o 4 líneas, como lo haría un meteorólogo leyendo los
modelos. Es un extra opcional y best-effort: sin llave, sin red o si
la respuesta no pasa la validación, el reporte sigue igual sin la
sección (nunca tumba el reporte ni el envío).

La llave (GEMINI_API_KEY) se guarda como secreto de GitHub; sin
tarjeta no hay manera de que genere un cobro. El modelo solo recibe
los números del pronóstico de 7 días que ya baja Open-Meteo (más el
resumen del ensemble de hoy); no recibe datos personales ni secretos.
"""

import os
import re
import time
import unicodedata
from datetime import datetime

import requests

from .utils import logger, DIAS_ESP

# Gemini 2.5 Flash: capa gratuita de Google AI Studio (sin tarjeta,
# 1,500 llamadas/día; el bot hace 1 al día).
MODELO_GEMINI = "gemini-2.5-flash"
URL_GEMINI = ("https://generativelanguage.googleapis.com/v1beta/models/"
              "{modelo}:generateContent")

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
        "récords. Si un día no tiene nada notable, no lo menciones. "
        "No saludes ni te presentes, solo el panorama.")
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


def obtener_narrativa_semanal(daily, ensemble=None, api_key=None,
                              modelo=MODELO_GEMINI):
    """
    Pide a Gemini la narrativa semanal (best-effort, nunca lanza
    excepciones). Devuelve el texto validado o None.

    La llave se toma del argumento o de GEMINI_API_KEY; sin llave no
    hay llamada de red. Máximo 2 intentos (timeout 20 s). Si la
    llamada falla, la respuesta viene vacía o el texto no pasa la
    validación, devuelve None y el reporte sigue sin la sección.
    La llave nunca se registra en el log.
    """
    try:
        llave = (api_key or os.environ.get("GEMINI_API_KEY") or "").strip()
        if not llave:
            logger.info("🤖 Narrador: sin llave GEMINI_API_KEY, "
                        "se omite la sección semanal")
            return None
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
        url = URL_GEMINI.format(modelo=modelo)
        headers = {"x-goog-api-key": llave,
                   "Content-Type": "application/json"}
        cuerpo = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.3,
                                 "maxOutputTokens": 300},
        }
        fechas = (daily or {}).get('time') or []
        for intento in range(1, 3):
            try:
                logger.info("🤖 Narrador: pidiendo panorama semanal a "
                            f"Gemini (intento {intento}/2)...")
                respuesta = requests.post(url, headers=headers, json=cuerpo,
                                          timeout=20)
                respuesta.raise_for_status()
                texto = _extraer_texto_gemini(respuesta.json())
                if not texto:
                    logger.warning("🤖 Narrador: Gemini respondió sin "
                                   "texto")
                    return None
                if validar_narrativa(texto, fechas):
                    logger.info("✅ Narrador: narrativa semanal lista")
                    return texto.strip()
                logger.warning("🤖 Narrador: la narrativa no pasó la "
                               "validación, se omite")
                return None
            except requests.Timeout:
                logger.warning("🤖 Narrador: timeout en intento "
                               f"{intento}/2")
            except requests.HTTPError as e:
                codigo = (e.response.status_code
                          if e.response is not None else "?")
                logger.warning("🤖 Narrador: error HTTP "
                               f"{codigo}, se omite")
                return None
            except requests.RequestException as e:
                logger.warning(f"🤖 Narrador: error de red ({e})")
            except Exception as e:
                logger.warning(f"🤖 Narrador: error inesperado ({e})")
                return None
            if intento < 2:
                time.sleep(2)
        logger.warning("🤖 Narrador: sin narrativa tras 2 intentos")
        return None
    except Exception as e:
        logger.warning(f"🤖 Narrador: error inesperado ({e})")
        return None

"""
Módulo para obtención de datos meteorológicos
"""

import requests
import time
from .utils import logger, validar_datos_api

# Configuración de Tempoal, Veracruz
LAT = 21.5189
LON = -98.3867
URL_API = "https://api.open-meteo.com/v1/forecast"

# Ensemble de Open-Meteo (probabilidades reales, sin llave):
# https://open-meteo.com/en/docs/ensemble-api
URL_ENSEMBLE = "https://ensemble-api.open-meteo.com/v1/ensemble"
# ECMWF IFS 0.25°: 51 corridas (50 miembros perturbados + control),
# alcance 15 días, se actualiza cada 6 h. Es el modelo que usa el
# pronóstico diario de la tarjeta.
MODELO_ENSEMBLE = "ecmwf_ifs025_ensemble"
# GFS Ensemble Seamless (NOAA GEFS): 31 corridas, alcance 35 días. Es
# el único ensemble gratuito que llega hasta Navidad cuando faltan
# más de 15 días (el ECMWF no alcanza); se usa SOLO para la gráfica
# de Navidad, no para el pronóstico diario.
MODELO_ENSEMBLE_NAVIDAD = "ncep_gefs_seamless"
# Umbral de lluvia medible en una hora/bloque (mm). Un miembro "dice
# que llueve" si su precipitación acumulada en el bloque supera esto.
UMBRAL_LLUVIA_ENSEMBLE_MM = 0.1


def _pedir_json_con_reintentos(url, params, max_reintentos, timeout,
                               descripcion):
    """
    GET con reintentos (misma pauta que obtener_datos_climaticos).

    Devuelve el dict JSON o None si todos los intentos fallaron. Nunca
    lanza excepciones: el ensemble es opcional y su fallo no debe
    tumbar el reporte.
    """
    for intento in range(1, max_reintentos + 1):
        try:
            logger.info(f"📡 {descripcion} — intento {intento}/{max_reintentos}...")
            response = requests.get(url, params=params, timeout=timeout)
            response.raise_for_status()
            return response.json()
        except requests.Timeout:
            logger.warning(f"⏱️  Timeout en intento {intento} ({descripcion})")
        except requests.HTTPError as e:
            logger.error(f"❌ Error HTTP {e.response.status_code} ({descripcion}): {e}")
        except requests.RequestException as e:
            logger.error(f"❌ Error de conexión ({descripcion}): {e}")
        except Exception as e:
            logger.error(f"❌ Error inesperado ({descripcion}): {e}")
        if intento < max_reintentos:
            time.sleep(3)
    logger.error(f"❌ Todos los intentos fallaron ({descripcion})")
    return None


def obtener_datos_ensemble(max_reintentos=3, timeout=20):
    """
    Obtiene el ensemble ECMWF para Tempoal (hoy, por hora).

    Devuelve el dict JSON de la Ensemble API con temperatura y
    precipitación por miembro (claves *_member01 ... *_member50),
    o None si falla. Best-effort: quien llama debe seguir sin él.
    """
    logger.info("🛰️  Conectando con el ensemble ECMWF...")
    params = {
        "latitude": LAT,
        "longitude": LON,
        "hourly": ["temperature_2m", "precipitation"],
        "models": MODELO_ENSEMBLE,
        "timezone": "America/Mexico_City",
        "forecast_days": 1,
    }
    data = _pedir_json_con_reintentos(
        URL_ENSEMBLE, params, max_reintentos, timeout, "ensemble ECMWF")
    if not data:
        return None
    hourly = data.get('hourly') or {}
    if not hourly.get('time') or not any(
            k.startswith('temperature_2m_member') for k in hourly):
        logger.error("❌ Ensemble ECMWF sin datos por miembro")
        return None
    n_miembros = sum(1 for k in hourly
                     if k.startswith('temperature_2m_member'))
    logger.info(f"✅ Ensemble recibido ({n_miembros} miembros)")
    return data


def obtener_datos_ensemble_navidad(max_reintentos=3, timeout=25):
    """
    Obtiene el ensemble GFS (35 días) para la gráfica de Navidad:
    temperatura mínima diaria por miembro.

    Devuelve el dict JSON de la Ensemble API o None si falla.
    Best-effort: sin estos datos simplemente no hay gráfica.
    """
    logger.info("🛰️  Conectando con el ensemble GFS (largo plazo)...")
    params = {
        "latitude": LAT,
        "longitude": LON,
        "daily": ["temperature_2m_min"],
        "models": MODELO_ENSEMBLE_NAVIDAD,
        "timezone": "America/Mexico_City",
        "forecast_days": 35,
    }
    data = _pedir_json_con_reintentos(
        URL_ENSEMBLE, params, max_reintentos, timeout, "ensemble GFS")
    if not data:
        return None
    daily = data.get('daily') or {}
    if not daily.get('time') or not any(
            k.startswith('temperature_2m_min_member') for k in daily):
        logger.error("❌ Ensemble GFS sin datos por miembro")
        return None
    n_miembros = sum(1 for k in daily
                     if k.startswith('temperature_2m_min_member'))
    logger.info(f"✅ Ensemble GFS recibido ({n_miembros} miembros, "
                f"{len(daily['time'])} días)")
    return data

def obtener_datos_climaticos(max_reintentos=3, timeout=20):
    """
    Obtiene datos meteorológicos de Open-Meteo con reintentos automáticos
    
    Args:
        max_reintentos: Número máximo de intentos
        timeout: Timeout en segundos para la petición
        
    Returns:
        dict: Datos meteorológicos o None si falla
    """
    logger.info("🛰️  Conectando con satélites meteorológicos...")
    
    params = {
        "latitude": LAT,
        "longitude": LON,
        "hourly": [
            "temperature_2m",
            "relative_humidity_2m",
            "apparent_temperature",
            "precipitation_probability",
            "precipitation",
            "weather_code",
            "wind_speed_10m",
            "wind_direction_10m",
            "wind_gusts_10m",
            "surface_pressure",
            "cloud_cover",
            "uv_index"
        ],
        "daily": [
            "weather_code",
            "temperature_2m_max",
            "temperature_2m_min",
            "apparent_temperature_max",
            "apparent_temperature_min",
            "sunrise",
            "sunset",
            "uv_index_max",
            "precipitation_sum",
            "precipitation_probability_max",
            "wind_speed_10m_max",
            "wind_gusts_10m_max",
            "wind_direction_10m_dominant"
        ],
        "current": [
            "temperature_2m",
            "relative_humidity_2m",
            "apparent_temperature",
            "weather_code",
            "wind_speed_10m"
        ],
        "timezone": "America/Mexico_City",
        "forecast_days": 7
    }
    
    for intento in range(1, max_reintentos + 1):
        try:
            logger.info(f"📡 Intento {intento}/{max_reintentos}...")
            
            response = requests.get(URL_API, params=params, timeout=timeout)
            response.raise_for_status()
            
            data = response.json()
            
            # Validar datos
            campos_requeridos = ['current', 'hourly', 'daily']
            if not validar_datos_api(data, campos_requeridos):
                raise ValueError("Datos incompletos en la respuesta")
            
            logger.info("✅ Datos meteorológicos recibidos correctamente")
            logger.info(f"   📊 Pronóstico para {len(data['daily']['time'])} días")
            logger.info(f"   🕐 Datos horarios: {len(data['hourly']['time'])} horas")
            
            return data
            
        except requests.Timeout:
            logger.warning(f"⏱️  Timeout en intento {intento}")
            if intento < max_reintentos:
                time.sleep(3)
                
        except requests.HTTPError as e:
            logger.error(f"❌ Error HTTP {e.response.status_code}: {e}")
            if intento < max_reintentos:
                time.sleep(3)
                
        except requests.RequestException as e:
            logger.error(f"❌ Error de conexión: {e}")
            if intento < max_reintentos:
                time.sleep(3)
                
        except ValueError as e:
            logger.error(f"❌ Error validando datos: {e}")
            return None
            
        except Exception as e:
            logger.error(f"❌ Error inesperado: {e}")
            if intento < max_reintentos:
                time.sleep(3)
    
    logger.error("❌ Todos los intentos de obtener datos fallaron")
    return None

def obtener_condiciones_actuales(data):
    """Extrae las condiciones meteorológicas actuales"""
    try:
        current = data['current']
        return {
            'temperatura': current.get('temperature_2m', 0),
            'sensacion': current.get('apparent_temperature', 0),
            'humedad': current.get('relative_humidity_2m', 0),
            'viento': current.get('wind_speed_10m', 0),
            'codigo_clima': current.get('weather_code', 0)
        }
    except Exception as e:
        logger.error(f"Error extrayendo condiciones actuales: {e}")
        return None
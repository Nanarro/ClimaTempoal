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
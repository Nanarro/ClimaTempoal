import requests
from datetime import datetime
import sys
import os

# --- CONFIGURACIÓN TELEGRAM (desde variables de entorno) ---
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID', '@climatempoal')

# --- CONFIGURACIÓN TEMPOAL ---
LAT = 21.5189
LON = -98.3867
URL_API = "https://api.open-meteo.com/v1/forecast"

DIAS_ESP = {
    "Monday": "LUNES", "Tuesday": "MARTES", "Wednesday": "MIÉRCOLES",
    "Thursday": "JUEVES", "Friday": "VIERNES", "Saturday": "SÁBADO",
    "Sunday": "DOMINGO"
}

def obtener_datos():
    """Obtiene datos meteorológicos de la API Open-Meteo"""
    print("📡 Intentando conectar con el satélite...")
    params = {
        "latitude": LAT, 
        "longitude": LON,
        "hourly": "temperature_2m,precipitation_probability,wind_gusts_10m",
        "daily": "temperature_2m_max,temperature_2m_min,wind_direction_10m_dominant,wind_gusts_10m_max,precipitation_sum",
        "timezone": "America/Mexico_City", 
        "forecast_days": 7
    }
    
    try:
        response = requests.get(URL_API, params=params, timeout=20)
        response.raise_for_status()
        data = response.json()
        
        # Validar que tenga los datos esperados
        if 'daily' not in data or 'hourly' not in data:
            print("❌ Respuesta incompleta de la API")
            return None
        
        print("✅ Datos del clima recibidos correctamente.")
        return data
        
    except requests.Timeout:
        print("❌ Timeout: El servidor tardó demasiado")
        return None
    except requests.RequestException as e:
        print(f"❌ ERROR DE CONEXIÓN: {e}")
        return None
    except Exception as e:
        print(f"❌ ERROR INESPERADO: {e}")
        return None

def analizar_riesgos(daily):
    """Analiza riesgos meteorológicos basados en datos diarios"""
    maxs = daily.get('temperature_2m_max', [])
    fechas = daily.get('time', [])
    dirs = daily.get('wind_direction_10m_dominant', [])
    vientos = daily.get('wind_gusts_10m_max', [])
    aguas = daily.get('precipitation_sum', [])

    # Validar que haya suficientes datos
    if len(maxs) < 2 or len(fechas) < 2:
        print("⚠️ Datos insuficientes para analizar riesgos")
        return []

    mensajes_alerta = []

    for i in range(len(fechas) - 1):
        caida = maxs[i] - maxs[i+1]
        es_norte = (dirs[i+1] >= 300 or dirs[i+1] <= 60)

        try:
            dt = datetime.strptime(fechas[i+1], "%Y-%m-%d")
            dia_nom = DIAS_ESP.get(dt.strftime("%A"), "DÍA")
            dia_num = dt.strftime("%d")
            fecha_txt = f"{dia_nom} {dia_num}"
        except Exception as e:
            print(f"⚠️ Error procesando fecha {fechas[i+1]}: {e}")
            continue

        # Detectar frente frío/norte
        if caida >= 4 and es_norte and vientos[i+1] >= 35:
            mensajes_alerta.append(
                f"⚠️ <b>{fecha_txt}: FRENTE FRÍO / NORTE</b>\n"
                f"   📉 Baja {round(caida,1)}°C | 💨 {vientos[i+1]} km/h"
            )
        # Detectar bajón térmico
        elif caida >= 5:
            mensajes_alerta.append(
                f"🧥 <b>{fecha_txt}: BAJÓN TÉRMICO</b>\n"
                f"   📉 Baja {round(caida,1)}°C (Se esperan {maxs[i+1]}°C)"
            )
        
        # Detectar lluvia intensa
        if aguas[i+1] > 20:
            mensajes_alerta.append(
                f"⛈️ <b>{fecha_txt}: LLUVIA INTENSA</b>\n"
                f"   💧 Acumulado: {aguas[i+1]} mm"
            )
        
        # Detectar calor extremo
        if maxs[i+1] > 38:
            mensajes_alerta.append(
                f"🔥 <b>{fecha_txt}: GOLPE DE CALOR</b>\n"
                f"   ☀️ Máxima: {maxs[i+1]}°C"
            )

    return mensajes_alerta

def formatear_linea_horaria(hora, temp, prob, wind):
    """Formatea una línea del pronóstico horario con iconos"""
    icono = "☁️"
    if prob > 70: 
        icono = "⛈️"
    elif prob > 40: 
        icono = "🌧️"
    elif temp < 16: 
        icono = "🥶"
    elif temp > 30: 
        icono = "🥵"
    elif 16 <= temp <= 22: 
        icono = "🍃"
    
    return f"<code>{hora}h|{icono} {temp:4.1f}°|💧{prob:>2}%|💨{wind:>3}k</code>\n"

def enviar_reporte(data):
    """Genera y envía el reporte meteorológico a Telegram"""
    print("📝 Generando reporte...")
    daily = data['daily']
    hourly = data['hourly']

    # Encabezado
    msg = f"🚨 <b>MONITOR CIVIL TEMPOAL</b> 🚨\n"
    msg += f"📅 <i>{datetime.now().strftime('%d/%m/%Y')}</i>\n"
    msg += f"🌡️ <b>HOY:</b> Max {daily['temperature_2m_max'][0]}°C | Min {daily['temperature_2m_min'][0]}°C\n"
    msg += "➖➖➖➖➖➖➖➖➖➖\n"

    # Pronóstico horario (24 horas)
    msg += "<b>PRONÓSTICO (24h):</b>\n"

    times = hourly['time']
    temps = hourly['temperature_2m']
    probs = hourly['precipitation_probability']
    gusts = hourly['wind_gusts_10m']

    for i in range(min(24, len(times))):
        # Mostrar cada 3 horas, o si hay eventos importantes
        if i % 3 == 0 or probs[i] > 50 or gusts[i] > 35:
            try:
                dt = datetime.fromisoformat(times[i])
                hora = dt.strftime("%H")
                msg += formatear_linea_horaria(hora, temps[i], probs[i], gusts[i])
            except Exception as e:
                print(f"⚠️ Error procesando hora {i}: {e}")
                continue

    msg += "➖➖➖➖➖➖➖➖➖➖\n"

    # Alertas de riesgos
    alertas = analizar_riesgos(daily)
    if alertas:
        msg += "📢 <b>ATENCIÓN - RIESGOS DETECTADOS:</b>\n\n"
        for alerta in alertas:
            msg += f"{alerta}\n\n"
    else:
        msg += "✅ <b>Sin riesgos extremos esta semana.</b>\n"

    msg += "➖➖➖➖➖➖➖➖➖➖\n"
    msg += "📡 <i>Reporte Protección Civil Tempoal datos satelitales de GFS/ECMWF</i>"

    # Envío a Telegram
    print(f"📤 Enviando mensaje a {TELEGRAM_CHAT_ID}...")
    
    if not TELEGRAM_TOKEN:
        print("❌ ERROR: TELEGRAM_TOKEN no está configurado")
        return False
    
    clean_token = TELEGRAM_TOKEN.strip()
    url = f"https://api.telegram.org/bot{clean_token}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": msg,
        "parse_mode": "HTML"
    }

    try:
        res = requests.post(url, data=payload, timeout=20)
        if res.status_code == 200:
            print("✅ ¡ÉXITO! Mensaje entregado en Telegram.")
            return True
        else:
            print(f"❌ ERROR TELEGRAM ({res.status_code}):")
            print(res.text)
            return False
    except Exception as e:
        print(f"❌ ERROR DE ENVÍO: {e}")
        return False

if __name__ == "__main__":
    print("🚀 Iniciando sistema...")
    
    # Validar variables de entorno
    if not TELEGRAM_TOKEN:
        print("❌ ERROR CRÍTICO: Falta la variable de entorno TELEGRAM_TOKEN")
        print("   Configúrala en GitHub Secrets")
        sys.exit(1)
    
    if not TELEGRAM_CHAT_ID:
        print("❌ ERROR CRÍTICO: Falta la variable de entorno TELEGRAM_CHAT_ID")
        sys.exit(1)
    
    # Obtener datos
    datos = obtener_datos()
    
    if datos:
        exito = enviar_reporte(datos)
        if exito:
            print("✅ Proceso completado exitosamente")
            sys.exit(0)
        else:
            print("❌ El reporte no pudo enviarse")
            sys.exit(1)
    else:
        print("⚠️ El programa terminó sin enviar nada por falta de datos.")
        sys.exit(1)

import requests
from datetime import datetime
import sys

# --- CONFIGURACIÓN TELEGRAM ---
TELEGRAM_TOKEN = "8237143784:AAGVL4Jvv6jIu0vEpZjjJmmfjObQ9Ead_k0"
TELEGRAM_CHAT_ID = "@climatempoal"

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
    print("📡 Intentando conectar con el satélite...")
    params = {
        "latitude": LAT, "longitude": LON,
        "hourly": "temperature_2m,precipitation_probability,wind_gusts_10m",
        "daily": "temperature_2m_max,temperature_2m_min,wind_direction_10m_dominant,wind_gusts_10m_max,precipitation_sum",
        "timezone": "America/Mexico_City", "forecast_days": 7
    }
    try:
        response = requests.get(URL_API, params=params, timeout=20)
        response.raise_for_status()
        print("✅ Datos del clima recibidos correctamente.")
        return response.json()
    except Exception as e:
        print(f"❌ ERROR DE CONEXIÓN: {e}")
        return None

def analizar_riesgos(daily):
    maxs = daily['temperature_2m_max']
    fechas = daily['time']
    dirs = daily['wind_direction_10m_dominant']
    vientos = daily['wind_gusts_10m_max']
    aguas = daily['precipitation_sum']

    mensajes_alerta = []

    for i in range(len(fechas) - 1):
        caida = maxs[i] - maxs[i+1]
        es_norte = (dirs[i+1] >= 300 or dirs[i+1] <= 60)

        dt = datetime.strptime(fechas[i+1], "%Y-%m-%d")
        dia_nom = DIAS_ESP.get(dt.strftime("%A"), "DÍA")
        dia_num = dt.strftime("%d")
        fecha_txt = f"{dia_nom} {dia_num}"

        if caida >= 4 and es_norte and vientos[i+1] >= 35:
            mensajes_alerta.append(f"⚠️ <b>{fecha_txt}: FRENTE FRÍO / NORTE</b>\n   📉 Baja {round(caida,1)}°C | 💨 {vientos[i+1]} km/h")
        elif caida >= 5:
            mensajes_alerta.append(f"🧥 <b>{fecha_txt}: BAJÓN TÉRMICO</b>\n   📉 Baja {round(caida,1)}°C (Se esperan {maxs[i+1]}°C)")
        elif aguas[i+1] > 20:
             mensajes_alerta.append(f"⛈️ <b>{fecha_txt}: LLUVIA INTENSA</b>\n   💧 Acumulado: {aguas[i+1]} mm")
        elif maxs[i+1] > 38:
             mensajes_alerta.append(f"🔥 <b>{fecha_txt}: GOLPE DE CALOR</b>\n   ☀️ Máxima: {maxs[i+1]}°C")

    return mensajes_alerta

def enviar_reporte(data):
    print("📝 Generando reporte...")
    daily = data['daily']
    hourly = data['hourly']

    msg = f"🚨 <b>MONITOR CIVIL TEMPOAL</b> 🚨\n"
    msg += f"📅 <i>{datetime.now().strftime('%d/%m/%Y')}</i>\n"
    msg += f"🌡️ <b>HOY:</b> Max {daily['temperature_2m_max'][0]}°C | Min {daily['temperature_2m_min'][0]}°C\n"
    msg += "➖➖➖➖➖➖➖➖➖➖\n"

    msg += "<b>PRONÓSTICO (24h):</b>\n"

    times = hourly['time']
    temps = hourly['temperature_2m']
    probs = hourly['precipitation_probability']
    gusts = hourly['wind_gusts_10m']

    for i in range(24):
        if i % 3 == 0 or probs[i] > 50 or gusts[i] > 35:
            dt = datetime.fromisoformat(times[i])
            hora = dt.strftime("%H")
            temp = temps[i]
            prob = probs[i]
            wind = gusts[i]

            icono = "☁️"
            if prob > 40: icono = "🌧️"
            if prob > 70: icono = "⛈️"
            if temp < 16: icono = "🥶"
            elif temp > 30: icono = "🥵"
            elif 16 <= temp <= 22: icono = "🍃"

            linea = f"<code>{hora}h|{icono} {temp:4.1f}°|💧{prob:>2}%|💨{wind:>3}k</code>\n"
            msg += linea

    msg += "➖➖➖➖➖➖➖➖➖➖\n"

    alertas = analizar_riesgos(daily)
    if alertas:
        msg += "📢 <b>ATENCIÓN - RIESGOS DETECTADOS:</b>\n\n"
        for alerta in alertas:
            msg += f"{alerta}\n\n"
    else:
        msg += "✅ <b>Sin riesgos extremos esta semana.</b>\n"

    msg += "➖➖➖➖➖➖➖➖➖➖\n"
    msg += "📡 <i>Reporte Protección Civil Tempoal datos satelitales de GFS/ECMWF</i>"

    # --- ENVÍO ---
    print(f"📤 Enviando mensaje a {TELEGRAM_CHAT_ID}...")
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
        else:
            print(f"❌ ERROR TELEGRAM ({res.status_code}):")
            print(res.text) # Aquí te dirá si el token está mal o el chat_id
    except Exception as e:
        print(f"❌ ERROR DE ENVÍO: {e}")

if __name__ == "__main__":
    print("🚀 Iniciando sistema...")
    datos = obtener_datos()
    if datos:
        enviar_reporte(datos)
    else:
        print("⚠️ El programa terminó sin enviar nada por falta de datos.")

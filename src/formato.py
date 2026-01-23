"""
Módulo de formateo de mensajes para Telegram
"""

from datetime import datetime
from .utils import logger, DIAS_ESP, formatear_fecha_completa

def parse_iso(dt_str):
    """Parsea ISO datetimes tolerando sufijo 'Z' y None."""
    if not dt_str:
        raise ValueError("Empty datetime string")
    # many APIs usan 'Z' para UTC, fromisoformat no lo acepta
    if dt_str.endswith("Z"):
        dt_str = dt_str[:-1] + "+00:00"
    return datetime.fromisoformat(dt_str)

def safe_get(seq, idx, default=0):
    """Acceso seguro a listas/iterables por índice."""
    try:
        return seq[idx]
    except Exception:
        return default

def get_current_value(current, *keys, default=0):
    """Busca la primera clave existente en current entre keys."""
    for k in keys:
        if k in current:
            return current.get(k)
    return default

def obtener_icono_clima(codigo):
    """
    Convierte código WMO en emoji descriptivo
    https://open-meteo.com/en/docs
    """
    iconos = {
        0: "☀️",      # Despejado
        1: "🌤️",     # Principalmente despejado
        2: "⛅",     # Parcialmente nublado
        3: "☁️",     # Nublado
        45: "🌫️",    # Niebla
        48: "🌫️",    # Niebla con escarcha
        51: "🌦️",    # Llovizna ligera
        53: "🌧️",    # Llovizna moderada
        55: "🌧️",    # Llovizna densa
        61: "🌧️",    # Lluvia ligera
        63: "🌧️",    # Lluvia moderada
        65: "⛈️",     # Lluvia intensa
        71: "🌨️",    # Nevada ligera
        73: "🌨️",    # Nevada moderada
        75: "❄️",     # Nevada intensa
        80: "🌦️",    # Chubascos ligeros
        81: "⛈️",     # Chubascos moderados
        82: "⛈️",     # Chubascos violentos
        95: "⛈️",     # Tormenta
        96: "⛈️",     # Tormenta con granizo ligero
        99: "⛈️"      # Tormenta con granizo fuerte
    }
    return iconos.get(codigo, "🌡️")

def formatear_linea_horaria(hora, temp, sensacion, prob_lluvia, viento, uv):
    """Formatea una línea del pronóstico horario"""
    # Determinar icono principal
    try:
        prob_lluvia_val = int(prob_lluvia)
    except Exception:
        prob_lluvia_val = 0

    try:
        temp_val = float(temp)
    except Exception:
        temp_val = 0.0

    try:
        viento_val = float(viento)
    except Exception:
        viento_val = 0.0

    if prob_lluvia_val > 70:
        icono = "⛈️"
    elif prob_lluvia_val > 40:
        icono = "🌧️"
    elif temp_val < 16:
        icono = "🥶"
    elif temp_val > 32:
        icono = "🥵"
    elif 18 <= temp_val <= 25:
        icono = "🍃"
    else:
        icono = "☁️"
    
    # Agregar indicadores especiales
    alertas = ""
    if viento_val > 40:
        alertas += "💨"
    if uv >= 8:
        alertas += "☀️"
    
    return (
        f"<code>{{hora}}h|{{icono}} {{temp_val:4.1f}}°"
        f"|💧{{prob_lluvia_val:>2}}%"
        f"|🌬{{viento_val:>3.0f}} km/h"
        f"{{(' ' + alertas) if alertas else ''}}</code>\n"
    )

def generar_resumen_ejecutivo(current, daily):
    """Genera resumen ejecutivo del día"""
    try:
        # 'current' puede venir con distintas claves según la fuente
        temp_actual = get_current_value(current, 'temperature_2m', 'temperature', 'temp', default=0)
        sensacion = get_current_value(current, 'apparent_temperature', 'feels_like', default=0)

        temp_max = safe_get(daily.get('temperature_2m_max', []), 0, default=0)
        temp_min = safe_get(daily.get('temperature_2m_min', []), 0, default=0)
        lluvia = safe_get(daily.get('precipitation_sum', []), 0, default=0)
        prob_lluvia = safe_get(daily.get('precipitation_probability_max', []), 0, default=0)
        
        resumen = "📋 <b>RESUMEN EJECUTIVO:</b> "
        
        # Condición de lluvia
        if lluvia > 20:
            resumen += "⛈️ Día muy lluvioso. "
        elif lluvia > 5:
            resumen += "🌧️ Lluvias moderadas. "
        elif prob_lluvia > 40:
            resumen += "☁️ Probabilidad de lluvia. "
        else:
            resumen += "☀️ Día seco. "
        
        # Temperatura
        if temp_max > 36:
            resumen += "🔥 Calor extremo. "
        elif temp_max > 32:
            resumen += "🥵 Calor intenso. "
        elif temp_max < 18:
            resumen += "🧥 Fresco. "
        elif temp_min < 10:
            resumen += "❄️ Madrugada fría. "
        else:
            resumen += "🌡️ Temperatura agradable. "
        
        # Recomendación
        if lluvia > 10:
            resumen += "☂️ Lleva paraguas."
        elif temp_max > 34:
            resumen += "💧 Hidrátate bien."
        elif temp_min < 12:
            resumen += "🧣 Abrígate en la mañana."
        
        return resumen + "\n"
        
    except Exception as e:
        logger.error(f"Error generando resumen: {{e}}")
        return ""

def generar_pronostico_3_dias(daily):
    """Genera pronóstico compacto de 3 días"""
    try:
        msg = "\n📅 <b>PRÓXIMOS 3 DÍAS:</b>\n"
        times = daily.get('time', [])
        total_days = len(times)
        # comenzar en 1 para el siguiente día
        for i in range(1, min(4, total_days)):
            fecha_str = safe_get(times, i, default=None)
            try:
                fecha = parse_iso(fecha_str) if fecha_str else datetime.strptime(fecha_str, "%Y-%m-%d")
            except Exception:
                # intentar parseo sin hora
                try:
                    fecha = datetime.strptime(fecha_str, "%Y-%m-%d")
                except Exception:
                    fecha = None

            # Resolver nombre del día en DIAS_ESP intentando varias claves
            dia = "DÍA"
            if fecha:
                dia_nombre = fecha.strftime("%A")
                dia = DIAS_ESP.get(dia_nombre) or DIAS_ESP.get(dia_nombre.lower()) or DIAS_ESP.get(fecha.weekday()) or "DÍA"

            temp_max = safe_get(daily.get('temperature_2m_max', []), i, default=None)
            temp_min = safe_get(daily.get('temperature_2m_min', []), i, default=None)
            lluvia = safe_get(daily.get('precipitation_sum', []), i, default=0)
            prob_lluvia = safe_get(daily.get('precipitation_probability_max', []), i, default=0)
            codigo = safe_get(daily.get('weather_code', []), i, default=0)
            
            icono = obtener_icono_clima(codigo)
            
            # Formatear temperaturas con fallback
            tmin_txt = f"{{round(temp_min)}}°" if temp_min is not None else "--"
            tmax_txt = f"{{round(temp_max)}}°C" if temp_max is not None else "--"
            
            msg += f"{{icono}} <b>{{dia}}</b>: {{tmin_txt}} - {{tmax_txt}}"
            
            if lluvia and lluvia > 5:
                msg += f" | 💧 {{round(lluvia)}}mm"
            elif prob_lluvia and prob_lluvia > 50:
                msg += f" | 💧 {{int(prob_lluvia)}}%"
            
            msg += "\n"
        
        return msg
        
    except Exception as e:
        logger.error(f"Error generando pronóstico 3 días: {{e}}")
        return ""

def generar_estadisticas_semana(daily):
    """Genera estadísticas de la semana"""
    try:
        temp_maxs = daily.get('temperature_2m_max', [])
        temp_mins = daily.get('temperature_2m_min', [])
        lluvia_list = daily.get('precipitation_sum', [])
        viento_list = daily.get('wind_gusts_10m_max', [])

        temp_max_semana = max(temp_maxs) if temp_maxs else 0
        temp_min_semana = min(temp_mins) if temp_mins else 0
        lluvia_total = sum(lluvia_list) if lluvia_list else 0
        viento_max = max(viento_list) if viento_list else 0
        
        msg = "\n📊 <b>ESTADÍSTICAS SEMANALES:</b>\n"
        msg += f"   🔥 Máxima: {{round(temp_max_semana)}}°C\n"
        msg += f"   🧊 Mínima: {{round(temp_min_semana)}}°C\n"
        msg += f"   💧 Lluvia acumulada: {{round(lluvia_total, 1)}} mm\n"
        msg += f"   💨 Viento máximo: {{round(viento_max)}} km/h\n"
        
        return msg
        
    except Exception as e:
        logger.error(f"Error generando estadísticas: {{e}}")
        return ""

def generar_mensaje_completo(data, alertas, eventos_especiales):
    """Genera el mensaje completo formateado para Telegram"""
    try:
        current = data.get('current', {})
        hourly = data.get('hourly', {})
        daily = data.get('daily', {})
        
        # Condiciones actuales (intentar múltiples claves)
        temp_actual = get_current_value(current, 'temperature_2m', 'temperature', 'temp', default=0)
        sensacion = get_current_value(current, 'apparent_temperature', 'feels_like', default=0)
        humedad = get_current_value(current, 'relative_humidity_2m', 'humidity', default=0)
        viento_actual = get_current_value(current, 'wind_speed_10m', 'wind_speed', 'wind', default=0)
        
        # Sol
        try:
            sunrise = parse_iso(safe_get(daily.get('sunrise', []), 0, default=None)).strftime("%H:%M")
        except Exception:
            sunrise = "--:--"
        try:
            sunset = parse_iso(safe_get(daily.get('sunset', []), 0, default=None)).strftime("%H:%M")
        except Exception:
            sunset = "--:--"
        
        # Construir mensaje
        msg = "🚨 <b>MONITOR CIVIL TEMPOAL</b> 🚨\n"
        msg += f"📅 <i>{{formatear_fecha_completa()}}</i>\n\n"
        
        # Resumen ejecutivo
        msg += generar_resumen_ejecutivo(
            {'temperatura': temp_actual, 'sensacion': sensacion, 'humedad': humedad},
            daily
        )
        
        msg += "\n━━━━━━━━━━━━━━━━━━━━\n\n"
        
        # Condiciones actuales
        msg += "🌡️ <b>CONDICIONES ACTUALES:</b>\n"
        msg += f"   Temperatura: {{round(float(temp_actual), 1)}}°C\n"
        msg += f"   Sensación térmica: {{round(float(sensacion), 1)}}°C\n"
        msg += f"   Humedad: {{round(float(humedad), 1)}}%\n"
        msg += f"   Viento: {{round(float(viento_actual), 1)}} km/h\n"
        msg += f"   🌅 Amanecer: {{sunrise}} | 🌇 Atardecer: {{sunset}}\n"
        
        msg += "\n━━━━━━━━━━━━━━━━━━━━\n"
        
        # Pronóstico horario (24h)
        msg += "\n<b>PRONÓSTICO HORARIO (24h):</b>\n"
        
        times = hourly.get('time', [])
        temps = hourly.get('temperature_2m', [])
        sensaciones = hourly.get('apparent_temperature', [])
        probs = hourly.get('precipitation_probability', [])
        vientos = hourly.get('wind_gusts_10m', [])
        uv_indices = hourly.get('uv_index', [0] * len(times))
        
        for i in range(min(24, len(times))):
            # Mostrar cada 3 horas o eventos importantes
            try:
                prob_i = safe_get(probs, i, default=0)
                viento_i = safe_get(vientos, i, default=0)
                uv_i = safe_get(uv_indices, i, default=0)
                if i % 3 == 0 or prob_i > 60 or viento_i > 40 or uv_i > 8:
                    dt = parse_iso(times[i]) if times[i].endswith('Z') or 'T' in times[i] else datetime.strptime(times[i], "%Y-%m-%dT%H:%M")
                    hora = dt.strftime("%H")
                    msg += formatear_linea_horaria(
                        hora,
                        safe_get(temps, i, default=0),
                        safe_get(sensaciones, i, default=0),
                        prob_i,
                        viento_i,
                        uv_i
                    )
            except Exception as e:
                logger.warning(f"Error formateando hora {{i}}: {{e}}")
        
        msg += "\n━━━━━━━━━━━━━━━━━━━━\n"
        
        # Pronóstico 3 días
        msg += generar_pronostico_3_dias(daily)
        
        msg += "\n━━━━━━━━━━━━━━━━━━━━\n"
        
        # Eventos especiales
        if eventos_especiales:
            msg += "\n⚡ <b>EVENTOS ESPECIALES (24h):</b>\n\n"
            for evento in eventos_especiales:
                msg += f"{{evento}}\n\n"
            msg += "━━━━━━━━━━━━━━━━━━━━\n"
        
        # Alertas
        if alertas:
            msg += "\n📢 <b>⚠️ ALERTAS METEOROLÓGICAS:</b>\n\n"
            for alerta in alertas:
                msg += f"{{alerta}}\n\n"
        else:
            msg += "\n✅ <b>Sin alertas meteorológicas esta semana</b>\n"
        
        msg += "\n━━━━━━━━━━━━━━━━━━━━\n"
        
        # Estadísticas (solo una vez)
        msg += generar_estadisticas_semana(daily)
        
        msg += "\n━━━━━━━━━━━━━━━━━━━━\n"
        msg += "\n📡 <i>Fuente: Open-Meteo (GFS/ECMWF)</i>\n"
        msg += "⚙️ <i>Sistema Automatizado v2.0</i>\n"
        msg += "🛡️ <i>Protección Civil Tempoal</i>"
        
        return msg
        
    except Exception as e:
        logger.error(f"Error generando mensaje completo: {{e}}")
        return None

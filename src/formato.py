"""
Módulo de formateo de mensajes para Telegram
"""

from datetime import datetime
from .utils import logger, DIAS_ESP, formatear_fecha_completa

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
    if prob_lluvia > 70:
        icono = "⛈️"
    elif prob_lluvia > 40:
        icono = "🌧️"
    elif temp < 16:
        icono = "🥶"
    elif temp > 32:
        icono = "🥵"
    elif 18 <= temp <= 25:
        icono = "🍃"
    else:
        icono = "☁️"
    
    # Agregar indicadores especiales
    alertas = ""
    if viento > 40:
        alertas += "💨"
    if uv >= 8:
        alertas += "☀️"
    
    return (
        f"<code>{hora}h|{icono} {temp:4.1f}°"
        f"|💧{prob_lluvia:>2}%"
        f"|🌬{viento:>2.0f}k"
        f"{' ' + alertas if alertas else ''}</code>\n"
    )

def generar_resumen_ejecutivo(current, daily):
    """Genera resumen ejecutivo del día"""
    try:
        temp_actual = current.get('temperatura', 0)
        temp_max = daily['temperature_2m_max'][0]
        temp_min = daily['temperature_2m_min'][0]
        lluvia = daily['precipitation_sum'][0]
        prob_lluvia = daily.get('precipitation_probability_max', [0])[0]
        
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
        logger.error(f"Error generando resumen: {e}")
        return ""

def generar_pronostico_3_dias(daily):
    """Genera pronóstico compacto de 3 días"""
    try:
        msg = "\n📅 <b>PRÓXIMOS 3 DÍAS:</b>\n"
        
        for i in range(1, min(4, len(daily['time']))):
            fecha = datetime.strptime(daily['time'][i], "%Y-%m-%d")
            dia = DIAS_ESP.get(fecha.strftime("%A"), "DÍA")
            
            temp_max = daily['temperature_2m_max'][i]
            temp_min = daily['temperature_2m_min'][i]
            lluvia = daily['precipitation_sum'][i]
            prob_lluvia = daily.get('precipitation_probability_max', [0] * 7)[i]
            codigo = daily.get('weather_code', [0] * 7)[i]
            
            icono = obtener_icono_clima(codigo)
            
            msg += f"{icono} <b>{dia}</b>: {round(temp_min)}° - {round(temp_max)}°C"
            
            if lluvia > 5:
                msg += f" | 💧 {round(lluvia)}mm"
            elif prob_lluvia > 50:
                msg += f" | 💧 {prob_lluvia}%"
            
            msg += "\n"
        
        return msg
        
    except Exception as e:
        logger.error(f"Error generando pronóstico 3 días: {e}")
        return ""

def generar_estadisticas_semana(daily):
    """Genera estadísticas de la semana"""
    try:
        temp_max_semana = max(daily['temperature_2m_max'])
        temp_min_semana = min(daily['temperature_2m_min'])
        lluvia_total = sum(daily['precipitation_sum'])
        viento_max = max(daily['wind_gusts_10m_max'])
        
        msg = "\n📊 <b>ESTADÍSTICAS SEMANALES:</b>\n"
        msg += f"   🔥 Máxima: {round(temp_max_semana)}°C\n"
        msg += f"   🧊 Mínima: {round(temp_min_semana)}°C\n"
        msg += f"   💧 Lluvia acumulada: {round(lluvia_total, 1)} mm\n"
        msg += f"   💨 Viento máximo: {round(viento_max)} km/h\n"
        
        return msg
        
    except Exception as e:
        logger.error(f"Error generando estadísticas: {e}")
        return ""

def generar_mensaje_completo(data, alertas, eventos_especiales):
    """
    Genera el mensaje completo formateado para Telegram
    """
    try:
        current = data['current']
        hourly = data['hourly']
        daily = data['daily']
        
        # Condiciones actuales
        temp_actual = current.get('temperature_2m', 0)
        sensacion = current.get('apparent_temperature', 0)
        humedad = current.get('relative_humidity_2m', 0)
        viento_actual = current.get('wind_speed_10m', 0)
        
        # Sol
        sunrise = datetime.fromisoformat(daily['sunrise'][0]).strftime("%H:%M")
        sunset = datetime.fromisoformat(daily['sunset'][0]).strftime("%H:%M")
        
        # Construir mensaje
        msg = "🚨 <b>MONITOR CIVIL TEMPOAL</b> 🚨\n"
        msg += f"📅 <i>{formatear_fecha_completa()}</i>\n\n"
        
        # Resumen ejecutivo
        msg += generar_resumen_ejecutivo(
            {'temperatura': temp_actual, 'sensacion': sensacion, 'humedad': humedad},
            daily
        )
        
        msg += "\n━━━━━━━━━━━━━━━━━━━━\n\n"
        
        # Condiciones actuales
        msg += "🌡️ <b>CONDICIONES ACTUALES:</b>\n"
        msg += f"   Temperatura: {round(temp_actual, 1)}°C\n"
        msg += f"   Sensación térmica: {round(sensacion, 1)}°C\n"
        msg += f"   Humedad: {round(humedad)}%\n"
        msg += f"   Viento: {round(viento_actual, 1)} km/h\n"
        msg += f"   🌅 Amanecer: {sunrise} | 🌇 Atardecer: {sunset}\n"
        
        msg += "\n━━━━━━━━━━━━━━━━━━━━\n"
        
        # Pronóstico horario (24h)
        msg += "\n<b>PRONÓSTICO HORARIO (24h):</b>\n"
        
        times = hourly['time']
        temps = hourly['temperature_2m']
        sensaciones = hourly['apparent_temperature']
        probs = hourly['precipitation_probability']
        vientos = hourly['wind_gusts_10m']
        uv_indices = hourly.get('uv_index', [0] * len(times))
        
        for i in range(min(24, len(times))):
            # Mostrar cada 3 horas o eventos importantes
            if i % 3 == 0 or probs[i] > 60 or vientos[i] > 40 or uv_indices[i] > 8:
                try:
                    dt = datetime.fromisoformat(times[i])
                    hora = dt.strftime("%H")
                    msg += formatear_linea_horaria(
                        hora, temps[i], sensaciones[i],
                        probs[i], vientos[i], uv_indices[i]
                    )
                except Exception as e:
                    logger.warning(f"Error formateando hora {i}: {e}")
        
        msg += "\n━━━━━━━━━━━━━━━━━━━━\n"
        
        # Pronóstico 3 días
        msg += generar_pronostico_3_dias(daily)
        
        msg += "\n━━━━━━━━━━━━━━━━━━━━\n"
        
        # Eventos especiales
        if eventos_especiales:
            msg += "\n⚡ <b>EVENTOS ESPECIALES (24h):</b>\n\n"
            for evento in eventos_especiales:
                msg += f"{evento}\n\n"
            msg += "━━━━━━━━━━━━━━━━━━━━\n"
        
        # Alertas
        if alertas:
            msg += "\n📢 <b>⚠️ ALERTAS METEOROLÓGICAS:</b>\n\n"
            for alerta in alertas:
                msg += f"{alerta}\n\n"
        else:
            msg += "\n✅ <b>Sin alertas meteorológicas esta semana</b>\n"
        
        msg += "\n━━━━━━━━━━━━━━━━━━━━\n"
        
        # Estadísticas
        msg += generar_estadisticas_semana(daily)
        msg += generar_estadisticas_semana(daily)
        
        msg += "\n━━━━━━━━━━━━━━━━━━━━\n"
        msg += "\n📡 <i>Fuente: Open-Meteo (GFS/ECMWF)</i>\n"
        msg += "⚙️ <i>Sistema Automatizado v2.0</i>\n"
        msg += "🛡️ <i>Protección Civil Tempoal</i>"
        
        return msg
        
    except Exception as e:
        logger.error(f"Error generando mensaje completo: {e}")
        return None

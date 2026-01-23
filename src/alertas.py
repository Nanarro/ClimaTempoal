"""
Módulo de detección y análisis de riesgos meteorológicos
"""

from datetime import datetime
from .utils import logger, DIAS_ESP

def analizar_riesgos_climaticos(daily):
    """
    Analiza riesgos meteorológicos para los próximos 7 días
    
    Detecta:
    - Frentes fríos con viento norte
    - Bajones térmicos significativos
    - Lluvias intensas
    - Calor extremo
    - Heladas
    - Vientos peligrosos
    
    Returns:
        list: Lista de alertas formateadas
    """
    logger.info("🔍 Analizando riesgos meteorológicos...")
    
    try:
        maxs = daily.get('temperature_2m_max', [])
        mins = daily.get('temperature_2m_min', [])
        fechas = daily.get('time', [])
        dirs = daily.get('wind_direction_10m_dominant', [])
        vientos = daily.get('wind_gusts_10m_max', [])
        lluvias = daily.get('precipitation_sum', [])
        uv_index = daily.get('uv_index_max', [])
        
        if len(maxs) < 2 or len(fechas) < 2:
            logger.warning("⚠️  Datos insuficientes para análisis de riesgos")
            return []
        
        mensajes_alerta = []
        
        for i in range(len(fechas) - 1):
            try:
                # Calcular cambio de temperatura
                caida_temp = maxs[i] - maxs[i+1]
                
                # Determinar si es viento del norte
                es_norte = (dirs[i+1] >= 315 or dirs[i+1] <= 45)
                
                # Formatear fecha
                dt = datetime.strptime(fechas[i+1], "%Y-%m-%d")
                dia_nom = DIAS_ESP.get(dt.strftime("%A"), "DÍA")
                dia_num = dt.strftime("%d")
                mes_num = dt.strftime("%m")
                fecha_txt = f"{dia_nom} {dia_num}/{mes_num}"
                
                # 🌨️ FRENTE FRÍO / NORTE
                if caida_temp >= 4 and es_norte and vientos[i+1] >= 35:
                    intensidad = "MODERADO"
                    if vientos[i+1] >= 50:
                        intensidad = "INTENSO"
                    elif vientos[i+1] >= 65:
                        intensidad = "MUY INTENSO"
                    
                    mensajes_alerta.append(
                        f"🌨️ <b>{fecha_txt}: FRENTE FRÍO / NORTE {intensidad}</b>\n"
                        f"   📉 Descenso: {round(caida_temp, 1)}°C\n"
                        f"   💨 Vientos: {round(vientos[i+1])} km/h\n"
                        f"   🧣 Temperatura esperada: {round(maxs[i+1])}°C\n"
                        f"   ⚠️ Abrígate bien y protege cultivos"
                    )
                
                # 🧊 HELADA
                elif mins[i+1] <= 3:
                    mensajes_alerta.append(
                        f"🧊 <b>{fecha_txt}: RIESGO DE HELADA</b>\n"
                        f"   🌡️ Mínima: {round(mins[i+1], 1)}°C\n"
                        f"   ⚠️ Protege plantas y mascotas"
                    )
                
                # ❄️ FRÍO INTENSO (sin ser frente frío)
                elif caida_temp >= 5:
                    mensajes_alerta.append(
                        f"❄️ <b>{fecha_txt}: BAJÓN TÉRMICO</b>\n"
                        f"   📉 Descenso: {round(caida_temp, 1)}°C\n"
                        f"   🌡️ Se esperan {round(maxs[i+1])}°C\n"
                        f"   🧥 Prepara ropa abrigadora"
                    )
                
                # ⛈️ LLUVIA INTENSA
                if lluvias[i+1] > 50:
                    mensajes_alerta.append(
                        f"⛈️ <b>{fecha_txt}: LLUVIA MUY INTENSA</b>\n"
                        f"   💧 Acumulado esperado: {round(lluvias[i+1])} mm\n"
                        f"   ⚠️ Riesgo de inundaciones\n"
                        f"   🚫 Evita cruzar arroyos"
                    )
                elif lluvias[i+1] > 20:
                    mensajes_alerta.append(
                        f"🌧️ <b>{fecha_txt}: LLUVIA INTENSA</b>\n"
                        f"   💧 Acumulado: {round(lluvias[i+1])} mm\n"
                        f"   ☂️ No olvides paraguas"
                    )
                
                # 🔥 CALOR EXTREMO
                if maxs[i+1] > 38:
                    nivel_uv = uv_index[i+1] if i+1 < len(uv_index) else 0
                    mensajes_alerta.append(
                        f"🔥 <b>{fecha_txt}: CALOR EXTREMO</b>\n"
                        f"   🌡️ Máxima: {round(maxs[i+1])}°C\n"
                        f"   ☀️ Índice UV: {round(nivel_uv)}\n"
                        f"   💧 Hidrátate constantemente\n"
                        f"   ⚠️ Evita sol 11:00-16:00"
                    )
                elif maxs[i+1] > 35:
                    mensajes_alerta.append(
                        f"🥵 <b>{fecha_txt}: CALOR INTENSO</b>\n"
                        f"   🌡️ Máxima: {round(maxs[i+1])}°C\n"
                        f"   💧 Mantente hidratado"
                    )
                
                # 🌪️ VIENTOS PELIGROSOS
                if vientos[i+1] > 60 and caida_temp < 4:  # Vientos sin frente frío
                    mensajes_alerta.append(
                        f"🌪️ <b>{fecha_txt}: VIENTOS MUY FUERTES</b>\n"
                        f"   💨 Ráfagas: {round(vientos[i+1])} km/h\n"
                        f"   ⚠️ Asegura objetos sueltos\n"
                        f"   🏠 Evita estar bajo árboles"
                    )
                
                # ☀️ UV EXTREMO
                if i+1 < len(uv_index) and uv_index[i+1] >= 11:
                    mensajes_alerta.append(
                        f"☀️ <b>{fecha_txt}: RADIACIÓN UV EXTREMA</b>\n"
                        f"   📊 Índice UV: {round(uv_index[i+1])}\n"
                        f"   🧴 Usa protector solar cada 2 horas\n"
                        f"   🕶️ Lentes y sombrero obligatorios"
                    )
                    
            except Exception as e:
                logger.warning(f"Error analizando día {i}: {e}")
                continue
        
        logger.info(f"📢 {len(mensajes_alerta)} alertas detectadas")
        return mensajes_alerta
        
    except Exception as e:
        logger.error(f"Error en análisis de riesgos: {e}")
        return []

def detectar_eventos_especiales(hourly):
    """
    Detecta eventos especiales en las próximas 24 horas
    """
    try:
        eventos = []
        
        temps = hourly.get('temperature_2m', [])[:24]
        vientos = hourly.get('wind_gusts_10m', [])[:24]
        precipitacion = hourly.get('precipitation', [])[:24]
        
        # Detectar helada nocturna (00:00 - 06:00)
        temps_noche = temps[:6]
        if any(t <= 0 for t in temps_noche):
            eventos.append("❄️ <b>ALERTA DE HELADA</b> en la madrugada")
        
        # Detectar vientos sostenidos peligrosos
        vientos_fuertes = sum(1 for v in vientos if v > 40)
        if vientos_fuertes >= 8:
            eventos.append("🌪️ <b>VIENTOS FUERTES SOSTENIDOS</b> por más de 8 horas")
        
        # Detectar lluvia continua
        horas_lluvia = sum(1 for p in precipitacion if p > 1)
        if horas_lluvia >= 12:
            eventos.append("🌧️ <b>LLUVIA CONTINUA</b> por más de 12 horas")
        
        return eventos
        
    except Exception as e:
        logger.error(f"Error detectando eventos especiales: {e}")
        return []
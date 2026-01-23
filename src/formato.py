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
        
        # Estadísticas (AQUÍ ESTABA EL ERROR)
        msg += generar_estadisticas_semana(daily)  # ← Agregado (daily)
        
        msg += "\n━━━━━━━━━━━━━━━━━━━━\n"
        msg += "\n📡 <i>Fuente: Open-Meteo (GFS/ECMWF)</i>\n"
        msg += "⚙️ <i>Sistema Automatizado v2.0</i>\n"
        msg += "🛡️ <i>Protección Civil Tempoal</i>"
        
        return msg
        
    except Exception as e:
        logger.error(f"Error generando mensaje completo: {e}")
        return None

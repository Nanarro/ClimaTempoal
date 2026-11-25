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
        f"<code>{hora}h|{icono} {temp:4.1f}°C"
        f"|💧{prob_lluvia:>2}%"
        f"|💨{viento:>2.0f}km/h"
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
            dia_num = fecha.strftime("%d/%m")
            
            temp_max = daily['temperature_2m_max'][i]
            temp_min = daily['temperature_2m_min'][i]
            lluvia = daily['precipitation_sum'][i]
            prob_lluvia = daily.get('precipitation_probability_max', [0] * 7)[i]
            codigo = daily.get('weather_code', [0] * 7)[i]
            
            icono = obtener_icono_clima(codigo)
            
            msg += f"{icono} <b>{dia} {dia_num}</b>: {round(temp_min)}° - {round(temp_max)}°C"
            
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
        
        # Sol (opcional: si Open-Meteo no trae amanecer/atardecer, se
        # omite la línea y el reporte sigue; antes un solo campo
        # faltante tumbaba todo el mensaje)
        linea_sol = ""
        try:
            amanecer = daily.get('sunrise') or []
            atardecer = daily.get('sunset') or []
            sunrise = datetime.fromisoformat(amanecer[0]).strftime("%H:%M")
            sunset = datetime.fromisoformat(atardecer[0]).strftime("%H:%M")
            linea_sol = f"   Amanecer: {sunrise} | Atardecer: {sunset}\n"
        except (IndexError, ValueError, TypeError):
            logger.warning("Sin datos de amanecer/atardecer, se omite la línea")
        
        # Construir mensaje
        msg = "🚨 <b>MONITOREO PROTECCIÓN CIVIL TEMPOAL</b> 🚨\n"
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
        msg += linea_sol
        
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
        
        msg += "\n━━━━━━━━━━━━━━━━━━━━\n"
        msg += "\n📡 <i>Fuente: Open-Meteo (GFS/ECMWF)</i>\n"
        msg += "⚙️ <i>Sistema Automatizado v2.0</i>\n"
        msg += "🛡️ <i>Protección Civil Tempoal</i>"
        
        return msg
        
    except Exception as e:
        logger.error(f"Error generando mensaje completo: {e}")
        return None

# ---------------------------------------------------------------------------
# Tarjeta diaria: bloques mañana / tarde / noche y conclusiones narradas
# ---------------------------------------------------------------------------

BLOQUES_DIA = [
    ("MAÑANA", "06–12 h", 6, 12),
    ("TARDE", "12–18 h", 12, 18),
    ("NOCHE", "18–00 h", 18, 24),
]


def direccion_viento_texto(grados):
    """Convierte grados (0-360) a punto cardinal en español (8 sectores)."""
    if grados is None:
        return None
    sectores = ["NORTE", "NORESTE", "ESTE", "SURESTE",
                "SUR", "SUROESTE", "OESTE", "NOROESTE"]
    idx = int(((float(grados) + 22.5) % 360) // 45)
    return sectores[idx]


def _direccion_dominante(direcciones):
    """Dirección más frecuente entre una lista de grados."""
    if not direcciones:
        return None
    sectores = [direccion_viento_texto(d) for d in direcciones]
    return max(set(sectores), key=sectores.count)


def _promedio(valores):
    """Promedio redondeado a 1 decimal, o None si no hay valores."""
    if not valores:
        return None
    return round(sum(valores) / len(valores), 1)


def resumir_bloque(datos, hora_inicio, hora_fin):
    """
    Resume un bloque horario (ej. 06-12 h) del día actual.

    Usa los datos horarios de Open-Meteo. Si el bloque no tiene datos
    horarios (por ejemplo, una corrida tardía), aproxima con el resumen
    diario para que la tarjeta nunca falle por falta de datos.
    """
    hourly = datos.get('hourly', {}) or {}
    daily = datos.get('daily', {}) or {}
    tiempos = hourly.get('time', []) or []
    hoy = (daily.get('time') or [None])[0]

    indices = []
    for i, t in enumerate(tiempos):
        try:
            dt = datetime.fromisoformat(t)
        except (ValueError, TypeError):
            continue
        if dt.strftime("%Y-%m-%d") == hoy and hora_inicio <= dt.hour < hora_fin:
            indices.append(i)

    def _vals(clave):
        arr = hourly.get(clave) or []
        return [arr[i] for i in indices
                if i < len(arr) and arr[i] is not None]

    temps = _vals('temperature_2m')
    if not temps:
        # Sin datos horarios: aproximación con el resumen diario
        maxs = daily.get('temperature_2m_max') or []
        mins = daily.get('temperature_2m_min') or []
        probs = daily.get('precipitation_probability_max') or []
        vientos = daily.get('wind_speed_10m_max') or []
        dirs = daily.get('wind_direction_10m_dominant') or []
        media = None
        if maxs and mins:
            media = round((maxs[0] + mins[0]) / 2, 1)
        return {
            'temp_media': media,
            'sensacion_media': media,
            'temp_min': round(mins[0], 1) if mins else None,
            'temp_max': round(maxs[0], 1) if maxs else None,
            'prob_max': probs[0] if probs else 0,
            'lluvia_mm': round(sum(hourly.get('precipitation') or []) or
                               (daily.get('precipitation_sum') or [0])[0], 1),
            'viento_dir': direccion_viento_texto(dirs[0]) if dirs else None,
            'viento_min': None,
            'viento_max': round(vientos[0], 1) if vientos else None,
            'rafaga_max': None,
            'presion_media': None,
            'nubosidad_media': None,
            'codigo': (daily.get('weather_code') or [None])[0],
            'estimado': True,
        }

    sens = _vals('apparent_temperature')
    probs = _vals('precipitation_probability')
    lluvias = _vals('precipitation')
    vientos = _vals('wind_speed_10m')
    rafagas = _vals('wind_gusts_10m')
    dirs = _vals('wind_direction_10m')
    presiones = _vals('surface_pressure')
    nubes = _vals('cloud_cover')
    codigos = _vals('weather_code')

    return {
        'temp_media': _promedio(temps),
        'sensacion_media': _promedio(sens) if sens else _promedio(temps),
        'temp_min': round(min(temps), 1),
        'temp_max': round(max(temps), 1),
        'prob_max': max(probs) if probs else 0,
        'lluvia_mm': round(sum(lluvias), 1) if lluvias else 0,
        'viento_dir': _direccion_dominante(dirs),
        'viento_min': round(min(vientos), 1) if vientos else None,
        'viento_max': round(max(vientos), 1) if vientos else None,
        'rafaga_max': round(max(rafagas), 1) if rafagas else None,
        'presion_media': round(_promedio(presiones)) if presiones else None,
        'nubosidad_media': round(_promedio(nubes)) if nubes else None,
        'codigo': max(set(codigos), key=codigos.count) if codigos else None,
        'estimado': False,
    }


def obtener_bloques_diarios(datos, ensemble=None):
    """
    Devuelve los 3 bloques del día (mañana, tarde, noche) con su resumen.

    Si se pasa el `ensemble` (dict de la Ensemble API ECMWF), cada bloque
    trae además sus estadísticas reales: 'prob_lluvia_ens' (% de miembros
    con lluvia), 'temp_media_ens' y 'temp_spread' (desviación estándar
    entre miembros). En ese caso 'prob_max' pasa a ser la probabilidad
    real del ensemble (la determinista queda en 'prob_max_det'), para
    que tarjeta, etiquetas y conclusiones hablen con un solo número.
    Sin ensemble, todo sigue como antes (heurística).
    """
    daily = datos.get('daily', {}) or {}
    lluvias_7d = daily.get('precipitation_sum') or []
    lluvia_7d = round(sum(v for v in lluvias_7d if v is not None), 1)
    hoy = (daily.get('time') or [None])[0]
    bloques = []
    for nombre, horas, inicio, fin in BLOQUES_DIA:
        resumen = resumir_bloque(datos, inicio, fin)
        resumen['nombre'] = nombre
        resumen['horas'] = horas
        # Lluvia acumulada de la semana (mm): sirve para detectar sequía
        resumen['lluvia_7d'] = lluvia_7d
        if ensemble is not None:
            ens = extraer_ensemble_bloque(ensemble, inicio, fin, hoy)
            if ens:
                resumen.update(ens)
                resumen['prob_max_det'] = resumen.get('prob_max')
                resumen['prob_max'] = ens['prob_lluvia_ens']
        bloques.append(resumen)
    return bloques


# ---------------------------------------------------------------------------
# Ensemble: probabilidades reales a partir de los miembros
# ---------------------------------------------------------------------------

# Umbral de lluvia medible (mm acumulados en el bloque). Un miembro
# "dice que llueve" si su precipitación en el bloque supera esto.
# 0.1 mm es el mínimo que registra una estación: menos que eso es
# rocío, no lluvia.
UMBRAL_LLUVIA_ENSEMBLE_MM = 0.1


def _claves_miembros(seccion, variable):
    """Claves '<variable>_memberNN' ordenadas (miembros perturbados)."""
    prefijo = variable + "_member"
    return sorted(k for k in (seccion or {}) if k.startswith(prefijo))


def _desviacion_estandar(valores):
    """Desviación estándar poblacional, o 0.0 si no hay dispersión."""
    if len(valores) < 2:
        return 0.0
    media = sum(valores) / len(valores)
    return (sum((v - media) ** 2 for v in valores) / len(valores)) ** 0.5


def extraer_ensemble_bloque(ensemble, hora_inicio, hora_fin, fecha_hoy):
    """
    Resume el ensemble ECMWF para un bloque horario del día actual.

    Devuelve None si no hay datos útiles (sin claves de miembro, sin
    horas del bloque o sin valores válidos).

    - prob_lluvia_ens: % de miembros cuya lluvia acumulada en el
      bloque supera UMBRAL_LLUVIA_ENSEMBLE_MM (0.1 mm).
    - temp_media_ens: media de las temperaturas medias de bloque de
      cada miembro.
    - temp_spread: desviación estándar entre miembros de esa media
      (°C). Es la medida real de incertidumbre: poca dispersión =
      los miembros coinciden; mucha = no se ponen de acuerdo.
    - n_miembros: cuántos miembros participaron.
    """
    hourly = (ensemble or {}).get('hourly', {}) or {}
    tiempos = hourly.get('time', []) or []
    claves_temp = _claves_miembros(hourly, 'temperature_2m')
    claves_lluvia = _claves_miembros(hourly, 'precipitation')
    if not claves_temp or not claves_lluvia or not fecha_hoy:
        return None

    indices = []
    for i, t in enumerate(tiempos):
        try:
            dt = datetime.fromisoformat(t)
        except (ValueError, TypeError):
            continue
        if dt.strftime("%Y-%m-%d") == fecha_hoy \
                and hora_inicio <= dt.hour < hora_fin:
            indices.append(i)
    if not indices:
        return None

    medias_temp = []
    con_lluvia = 0
    n = 0
    for kt, kl in zip(claves_temp, claves_lluvia):
        arr_t = hourly.get(kt) or []
        arr_p = hourly.get(kl) or []
        temps = [arr_t[i] for i in indices
                 if i < len(arr_t) and arr_t[i] is not None]
        precs = [arr_p[i] for i in indices
                 if i < len(arr_p) and arr_p[i] is not None]
        if not temps or not precs:
            continue
        medias_temp.append(sum(temps) / len(temps))
        if sum(precs) > UMBRAL_LLUVIA_ENSEMBLE_MM:
            con_lluvia += 1
        n += 1
    if n == 0:
        return None

    return {
        'prob_lluvia_ens': round(100 * con_lluvia / n),
        'temp_media_ens': round(sum(medias_temp) / len(medias_temp), 1),
        'temp_spread': round(_desviacion_estandar(medias_temp), 1),
        'n_miembros': n,
    }


def etiqueta_bloque(resumen):
    """Etiqueta corta del bloque, estilo MeteoAlert (ej. NORTE LIGERO)."""
    prob = resumen.get('prob_max') or 0
    lluvia = resumen.get('lluvia_mm') or 0
    viento_dir = resumen.get('viento_dir')
    viento_max = resumen.get('viento_max') or 0
    nubes = resumen.get('nubosidad_media')

    if lluvia >= 10 or prob >= 80:
        return "LLUVIAS FUERTES" if lluvia >= 10 else "LLUVIAS"
    if prob >= 60:
        return "POSIBLES LLUVIAS"
    if viento_dir == "NORTE":
        if viento_max >= 40:
            return "NORTE FUERTE"
        if viento_max >= 20:
            return "NORTE MODERADO"
        if viento_max >= 10:
            return "NORTE LIGERO"
    if nubes is not None:
        if nubes >= 70:
            return "NUBLADO"
        if nubes >= 40:
            return "MEDIO NUBLADO"
        if nubes < 20 and prob < 20:
            return "DESPEJADO"
    if prob >= 40:
        return "LLUVIA LIGERA"
    return "PARCIALMENTE NUBLADO"


def nivel_confianza(bloques):
    """
    Nivel de confianza del pronóstico (BAJA / MEDIA / ALTA) y segmentos
    llenos de 4 para la barra de la tarjeta.

    Con ensemble (los bloques traen 'temp_spread' y 'prob_lluvia_ens'),
    la confianza es REAL: mide cuánto coinciden los miembros.
    - ALTA (4): dispersión media de temperatura ≤ 1.5 °C entre
      miembros Y en todos los bloques al menos el 80% de los miembros
      coincide en si llueve o no.
    - BAJA (2): dispersión media ≥ 3.0 °C (los miembros no se ponen
      de acuerdo en la temperatura) O en algún bloque el acuerdo sobre
      lluvia baja del 60% (casi un volado).
    - MEDIA (3): el resto.
    Los umbrales: 1.5 °C es un acuerdo estrecho para 24 h; 3 °C es
    un desacuerdo grande; 80% es consenso fuerte y 60% es casi azar.

    Sin ensemble, se usa la heurística de siempre (variación de la
    probabilidad de lluvia entre bloques + cambios de dirección del
    viento), para que la tarjeta nunca se quede sin barra.
    """
    spreads = [b.get('temp_spread') for b in bloques
               if b.get('temp_spread') is not None]
    probs_ens = [b.get('prob_lluvia_ens') for b in bloques
                 if b.get('prob_lluvia_ens') is not None]
    if spreads and probs_ens:
        spread_prom = sum(spreads) / len(spreads)
        acuerdo_min = min(max(p, 100 - p) for p in probs_ens)
        if spread_prom <= 1.5 and acuerdo_min >= 80:
            return ("ALTA", 4)
        if spread_prom >= 3.0 or acuerdo_min < 60:
            return ("BAJA", 2)
        return ("MEDIA", 3)

    # Heurística (respaldo sin ensemble): si la probabilidad de lluvia
    # varía mucho entre bloques o el viento cambia de dirección varias
    # veces en el día, el pronóstico es menos confiable (como cuando
    # MeteoAlert marca BAJA por la incertidumbre en horarios y
    # distribución de la lluvia).
    probs = [b.get('prob_max') or 0 for b in bloques]
    spread = (max(probs) - min(probs)) if probs else 0
    dirs = {b.get('viento_dir') for b in bloques if b.get('viento_dir')}
    if spread >= 60 or len(dirs) >= 3:
        return ("BAJA", 2)
    if spread <= 30 and len(dirs) <= 1:
        return ("ALTA", 4)
    return ("MEDIA", 3)


def _frase_lluvia(resumen):
    """Frase sobre lluvia para un bloque."""
    prob = resumen.get('prob_max') or 0
    mm = resumen.get('lluvia_mm') or 0
    if prob >= 70:
        frase = f"alto potencial de lluvias ({prob}% de probabilidad"
        if mm >= 5:
            frase += f", hasta {mm:.0f} mm acumulados"
        frase += "), pueden ser momentáneamente fuertes"
        return frase
    if prob >= 40:
        return f"probabilidad de lluvia del {prob}%, con chubascos ocasionales"
    if prob >= 20:
        return f"alguna llovizna o lluvia ligera ocasional ({prob}%)"
    return "sin lluvia esperada"


def _frase_viento(resumen):
    """Frase sobre viento para un bloque."""
    direccion = resumen.get('viento_dir')
    vmin = resumen.get('viento_min')
    vmax = resumen.get('viento_max')
    if not direccion or vmax is None:
        return None
    if vmax >= 40:
        intensidad = "fuerte"
    elif vmax >= 20:
        intensidad = "moderado"
    elif vmax >= 10:
        intensidad = "ligero"
    else:
        intensidad = "flojo"
    if vmin is not None and vmin != vmax:
        rango = f"de {vmin:.0f} a {vmax:.0f} km/h"
    else:
        rango = f"de {vmax:.0f} km/h"
    return f"viento del {direccion.lower()} {intensidad}, {rango}"


def _frase_temperatura(resumen):
    """Frase sobre temperatura para un bloque."""
    media = resumen.get('temp_media')
    if media is None:
        return None
    if media < 16:
        ambiente = "ambiente frío"
    elif media < 19:
        ambiente = "ambiente fresco"
    elif media <= 25:
        ambiente = "ambiente templado"
    elif media <= 30:
        ambiente = "ambiente cálido"
    else:
        ambiente = "ambiente muy caluroso"
    frase = (f"{ambiente}, temperatura media de {media:.0f}°C "
             f"(mín. {resumen.get('temp_min'):.0f}°, "
             f"máx. {resumen.get('temp_max'):.0f}°)")
    sensacion = resumen.get('sensacion_media')
    if sensacion is not None and abs(sensacion - media) >= 3:
        frase += f", sensación térmica de {sensacion:.0f}°C"
    return frase


def generar_conclusiones_bloques(datos, ensemble=None):
    """
    Genera una conclusión narrada por bloque (mañana, tarde, noche),
    estilo MeteoAlert. Devuelve una lista de 3 textos en HTML para Telegram.
    Con `ensemble`, las conclusiones usan la probabilidad real de lluvia.
    """
    try:
        bloques = obtener_bloques_diarios(datos, ensemble=ensemble)
        conclusiones = []
        for bloque in bloques:
            partes = [_frase_lluvia(bloque)]
            viento = _frase_viento(bloque)
            if viento:
                partes.append(viento)
            temperatura = _frase_temperatura(bloque)
            if temperatura:
                partes.append(temperatura)
            texto = ". ".join(
                p[:1].upper() + p[1:] if p else p for p in partes) + "."
            conclusiones.append(
                f"• <b>{bloque['nombre']} ({bloque['horas']}):</b> {texto}")
        return conclusiones
    except Exception as e:
        logger.error(f"Error generando conclusiones por bloque: {e}")
        return []


def generar_caption_tarjeta(datos, ensemble=None):
    """
    Caption corto para la foto de la tarjeta (límite de Telegram: 1024
    caracteres). Incluye la fecha y las 3 conclusiones por bloque.
    Con `ensemble`, las conclusiones usan la probabilidad real de lluvia.
    """
    try:
        fecha = formatear_fecha_completa().split(" - ")[0]
        lineas = [f"📅 <b>{fecha} — TEMPOAL</b>", ""]
        lineas.extend(generar_conclusiones_bloques(datos, ensemble=ensemble))
        caption = "\n".join(lineas)
        if len(caption) <= 1000:
            return caption
        # Recortar por viñetas completas para no superar el límite
        recortado = [lineas[0], ""]
        for viñeta in lineas[2:]:
            if len("\n".join(recortado + [viñeta])) > 1000:
                break
            recortado.append(viñeta)
        return "\n".join(recortado)
    except Exception as e:
        logger.error(f"Error generando caption de tarjeta: {e}")
        return "📅 <b>PRONÓSTICO DEL DÍA — TEMPOAL</b>"

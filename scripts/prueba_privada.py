#!/usr/bin/env python3
"""
Prueba privada del bot SIN enviar nada a Telegram.

Ejecuta exactamente los mismos pasos que main.py (validar configuración,
obtener datos, analizar riesgos, generar reporte y tarjeta) y se detiene
antes del envío. Sirve para cazar errores o bugs antes de la corrida real.

Uso (desde la raíz del repo):
    python scripts/prueba_privada.py

Si Open-Meteo no responde, usa datos de ejemplo para probar el resto
del pipeline. Genera dos archivos para revisar:
    - tarjeta_prueba.png  (la tarjeta tal como se enviaría)
    - reporte_prueba.txt  (el texto tal como se enviaría)

No toca secretos ni envía mensajes: es 100% privado.
"""

import os
import sys
from datetime import datetime, timedelta

# Raíz del repo en el path (el script vive en scripts/)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# Valores falsos solo para pasar la validación (nunca se usan para enviar)
os.environ.setdefault('TELEGRAM_TOKEN', 'x' * 45)
os.environ.setdefault('TELEGRAM_CHAT_ID', '-1000000000000')

from src.alertas import analizar_riesgos_climaticos, detectar_eventos_especiales
from src.clima import (
    obtener_datos_climaticos,
    obtener_datos_ensemble,
    obtener_datos_ensemble_navidad,
)
from src.formato import generar_caption_tarjeta, generar_mensaje_completo
from src.grafica_navidad import (
    calcular_probabilidades_frio,
    generar_grafica_navidad,
    rango_navidad,
    temporada_navidad,
)
from src.narrador import obtener_narrativa_semanal
from src.tarjeta import generar_tarjeta_diaria
from src.telegram_bot import validar_configuracion_telegram
from src.utils import DIAS_ESP


def _datos_ejemplo():
    """Datos sintéticos con la forma real de Open-Meteo (día de norte)."""
    hoy = datetime.now().strftime("%Y-%m-%d")
    horas, temps, sens, probs = [], [], [], []
    lluvias, vientos, rafagas, dirs = [], [], [], []
    presiones, nubes, codigos, uvs = [], [], [], []
    for h in range(24):
        horas.append(f"{hoy}T{h:02d}:00")
        temps.append(17.0 + 0.2 * h if h < 12 else 21.0 - 0.3 * (h - 12))
        sens.append(temps[-1] - 1.0)
        probs.append(80 if h < 12 else (60 if h < 18 else 40))
        lluvias.append(0.5 if h < 12 else 0.1)
        vientos.append(12.0 + h * 0.8)
        rafagas.append(vientos[-1] * 1.5)
        dirs.append(350.0)
        presiones.append(1019.0 + h * 0.1)
        nubes.append(90 if h < 12 else 60)
        codigos.append(61 if h < 12 else 3)
        uvs.append(0.0 if h < 7 or h > 17 else 5.0)
    dias = [(datetime.now() + timedelta(days=i)).strftime("%Y-%m-%d")
            for i in range(7)]
    return {
        'hourly': {
            'time': horas, 'temperature_2m': temps,
            'apparent_temperature': sens,
            'precipitation_probability': probs, 'precipitation': lluvias,
            'weather_code': codigos, 'wind_speed_10m': vientos,
            'wind_gusts_10m': rafagas, 'wind_direction_10m': dirs,
            'surface_pressure': presiones, 'cloud_cover': nubes,
            'uv_index': uvs,
        },
        'daily': {
            'time': dias,
            'temperature_2m_max': [21.0, 22.0, 23.0, 22.0, 21.0, 20.0, 20.0],
            'temperature_2m_min': [16.0, 15.0, 16.0, 15.0, 14.0, 14.0, 13.0],
            'apparent_temperature_max': [20.0, 21.0, 22.0, 21.0, 20.0, 19.0, 19.0],
            'apparent_temperature_min': [15.0, 14.0, 15.0, 14.0, 13.0, 13.0, 12.0],
            'sunrise': [f"{d}T06:30" for d in dias],
            'sunset': [f"{d}T17:45" for d in dias],
            'uv_index_max': [5.0, 6.0, 6.0, 5.0, 5.0, 4.0, 4.0],
            'precipitation_probability_max': [80, 60, 40, 30, 20, 10, 10],
            'precipitation_sum': [5.0, 3.0, 1.0, 0.5, 0.0, 0.0, 0.0],
            'wind_speed_10m_max': [30.0, 25.0, 20.0, 18.0, 15.0, 12.0, 12.0],
            'wind_gusts_10m_max': [45.0, 38.0, 30.0, 27.0, 22.0, 18.0, 18.0],
            'wind_direction_10m_dominant': [350.0, 340.0, 20.0, 45.0, 90.0, 90.0, 90.0],
            'weather_code': [61, 61, 3, 2, 1, 0, 0],
        },
        'current': {
            'temperature_2m': 17.0, 'apparent_temperature': 16.0,
            'relative_humidity_2m': 85, 'weather_code': 61,
            'wind_speed_10m': 15.0,
        },
    }


def main():
    errores = []

    print("PASO 1: Validando configuración...")
    if validar_configuracion_telegram():
        print("  ✅ OK")
    else:
        errores.append("configuración inválida")
        print("  ❌ FALLÓ")

    print("PASO 2: Obteniendo datos meteorológicos...")
    datos = obtener_datos_climaticos(max_reintentos=3)
    if datos:
        print("  ✅ Datos reales (Open-Meteo)")
    else:
        print("  ⚠️  Open-Meteo no respondió, uso datos de ejemplo")
        datos = _datos_ejemplo()

    print("PASO 2b: Obteniendo ensemble ECMWF (probabilidades reales)...")
    ensemble = None
    try:
        ensemble = obtener_datos_ensemble()
    except Exception as e:
        print(f"  ⚠️  Ensemble no disponible ({e})")
    if ensemble:
        print("  ✅ Ensemble real (ECMWF)")
    else:
        print("  ⚠️  Sin ensemble: la tarjeta usará la heurística de siempre")

    print("PASO 2c: Narrador semanal SIN llave (no debe haber red ni crash)...")
    os.environ.pop('GEMINI_API_KEY', None)  # la prueba es sin llave
    try:
        narrativa_sin_llave = obtener_narrativa_semanal(
            datos['daily'], ensemble=ensemble, api_key=None)
    except Exception as e:
        errores.append(f"el narrador sin llave lanzó excepción: {e}")
        narrativa_sin_llave = "ERROR"
        print(f"  ❌ FALLÓ (lanzó excepción: {e})")
    if narrativa_sin_llave is None:
        print("  ✅ Devuelve None rápido, sin red ni crash")
    elif narrativa_sin_llave != "ERROR":
        print("  ⚠️  Había llave en el entorno y devolvió texto (no es error)")

    print("PASO 3: Analizando riesgos...")
    alertas = analizar_riesgos_climaticos(datos['daily'])
    eventos = detectar_eventos_especiales(datos['hourly'])
    print(f"  ✅ {len(alertas)} alertas, {len(eventos)} eventos")

    print("PASO 4: Generando reporte de texto...")
    mensaje = generar_mensaje_completo(datos, alertas, eventos,
                                      ensemble=ensemble)
    if mensaje:
        print(f"  ✅ Reporte generado ({len(mensaje)} caracteres)")
        with open('reporte_prueba.txt', 'w', encoding='utf-8') as f:
            f.write(mensaje)
    else:
        errores.append("no se pudo generar el reporte")
        print("  ❌ FALLÓ")

    print("PASO 4d: Reporte de muestra con la sección semanal...")
    # Ejemplo (NO es salida de Gemini: solo muestra dónde queda la
    # sección). Las 3 líneas se derivan de los datos reales del día.
    try:
        daily = datos['daily']
        fechas = daily['time']

        def _dia(i):
            fecha = datetime.strptime(fechas[i], "%Y-%m-%d")
            return f"{DIAS_ESP.get(fecha.strftime('%A'), 'Día')} {fecha.strftime('%d/%m')}"

        i_lluvia = max(range(len(fechas)),
                       key=lambda i: daily['precipitation_sum'][i])
        i_frio = min(range(len(fechas)),
                     key=lambda i: daily['temperature_2m_min'][i])
        i_calor = max(range(len(fechas)),
                      key=lambda i: daily['temperature_2m_max'][i])
        ejemplo_semana = (
            f"El {_dia(i_lluvia)} será el día más lluvioso de la semana, "
            f"con {round(daily['precipitation_sum'][i_lluvia], 1)} mm y "
            f"{round(daily['precipitation_probability_max'][i_lluvia])}% "
            f"de probabilidad.\n"
            f"El día más frío será el {_dia(i_frio)}, con mínima de "
            f"{round(daily['temperature_2m_min'][i_frio])} °C.\n"
            f"La máxima más alta llegará el {_dia(i_calor)}, con "
            f"{round(daily['temperature_2m_max'][i_calor])} °C.")
        mensaje_semana = generar_mensaje_completo(
            datos, alertas, eventos, ensemble=ensemble,
            semana_narrativa=ejemplo_semana)
        if mensaje_semana and "LA SEMANA EN TEMPOAL" in mensaje_semana:
            with open('reporte_muestra_semana.txt', 'w',
                      encoding='utf-8') as f:
                f.write(mensaje_semana)
            print("  ✅ Muestra guardada en reporte_muestra_semana.txt")
        else:
            errores.append("la muestra semanal no trae la sección")
            print("  ❌ FALLÓ")
    except Exception as e:
        errores.append(f"no se pudo generar la muestra semanal: {e}")
        print(f"  ❌ FALLÓ ({e})")

    print("PASO 4b: Generando tarjeta...")
    ruta_logo = os.path.join(os.path.dirname(__file__), '..', 'logo.png')
    ruta_tarjeta = generar_tarjeta_diaria(
        datos, 'tarjeta_prueba.png',
        ruta_logo=ruta_logo if os.path.exists(ruta_logo) else None,
        ensemble=ensemble)
    if ruta_tarjeta:
        caption = generar_caption_tarjeta(datos, ensemble=ensemble)
        print(f"  ✅ Tarjeta generada, caption {len(caption)} caracteres")
    else:
        errores.append("no se pudo generar la tarjeta")
        print("  ❌ FALLÓ")

    print("PASO 4c: Gráfica de Navidad (si es temporada)...")
    if temporada_navidad():
        ruta_navidad = None
        try:
            datos_gfs = obtener_datos_ensemble_navidad()
            if datos_gfs:
                rango = rango_navidad()
                if rango:
                    probs = calcular_probabilidades_frio(
                        datos_gfs, rango[0], rango[1])
                    if probs:
                        ruta_navidad = generar_grafica_navidad(
                            probs, 'grafica_navidad_prueba.png')
        except Exception as e:
            print(f"  ⚠️  Gráfica no disponible ({e})")
        if ruta_navidad:
            print("  ✅ Gráfica de Navidad generada")
        else:
            print("  ⚠️  Sin gráfica (sin datos GFS), el resto sigue igual")
    else:
        print("  ⏭️  Fuera de temporada, se omite")

    print("PASO 5: OMITIDO — nada se envió a Telegram")
    print()
    if errores:
        print(f"❌ PRUEBA CON ERRORES: {errores}")
        return 1
    print("✅ PRUEBA PRIVADA OK — todo funcionó, nada se envió")
    print("   Revisa tarjeta_prueba.png y reporte_prueba.txt")
    return 0


if __name__ == "__main__":
    sys.exit(main())

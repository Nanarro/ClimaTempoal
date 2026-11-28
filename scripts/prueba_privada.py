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

Y dos muestras con las secciones de Gemini (ejemplos derivados de
los datos reales, NO salida de Gemini):
    - reporte_muestra_semana.txt  (la sección semanal)
    - reporte_muestra_gemini.txt  (día + semana + alertas)

No toca secretos ni envía mensajes: es 100% privado.
"""

import os
import re
import sys
from datetime import date, datetime, timedelta

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
    distribucion_minima_navidad,
    generar_grafica_navidad,
    temporada_navidad,
)
from src.narrador import (
    obtener_explicacion_alertas,
    obtener_interpretacion_navidad,
    obtener_narrativa_dia,
    obtener_narrativa_semanal,
)
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


def _ejemplo_semana(datos):
    """Ejemplo de narrativa semanal derivado de los datos reales."""
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
    return (
        f"El {_dia(i_lluvia)} será el día más lluvioso de la semana, "
        f"con {round(daily['precipitation_sum'][i_lluvia], 1)} mm y "
        f"{round(daily['precipitation_probability_max'][i_lluvia])}% "
        f"de probabilidad.\n"
        f"El día más frío será el {_dia(i_frio)}, con mínima de "
        f"{round(daily['temperature_2m_min'][i_frio])} °C.\n"
        f"La máxima más alta llegará el {_dia(i_calor)}, con "
        f"{round(daily['temperature_2m_max'][i_calor])} °C.")


def _ejemplo_dia(datos, ensemble=None):
    """Ejemplo de narrativa del día derivado de los datos reales."""
    from src.formato import obtener_bloques_diarios
    daily = datos['daily']
    hourly = datos.get('hourly') or {}
    lineas = []
    try:
        bloques = obtener_bloques_diarios(datos, ensemble=ensemble)
    except Exception:
        bloques = []
    if bloques:
        mas_lluvia = max(bloques, key=lambda b: b.get('prob_max') or 0)
        menos_lluvia = min(bloques, key=lambda b: b.get('prob_max') or 0)
        nombre = (mas_lluvia.get('nombre') or '').lower()
        prob = round(mas_lluvia.get('prob_max') or 0)
        linea = (f"La lluvia más fuerte será {nombre}, con {prob}% de "
                 "probabilidad")
        if ((mas_lluvia.get('prob_max') or 0)
                - (menos_lluvia.get('prob_max') or 0) >= 30):
            linea += (" y se irá calmando hacia "
                      f"{(menos_lluvia.get('nombre') or '').lower()}")
        lineas.append(linea + ".")
    mins = [v for v in (daily.get('temperature_2m_min') or [])
            if v is not None]
    maxs = [v for v in (daily.get('temperature_2m_max') or [])
            if v is not None]
    if mins and maxs:
        lineas.append(f"La temperatura irá de {round(min(mins))} °C a "
                      f"{round(max(maxs))} °C.")
    presiones = [p for p in (hourly.get('surface_pressure') or [])
                 if p is not None]
    if len(presiones) >= 2:
        delta = round(presiones[-1] - presiones[0], 1)
        if delta <= -3:
            lineas.append("La presión viene bajando: la lluvia se mantendrá.")
        elif delta >= 3:
            lineas.append(
                "La presión viene subiendo: el tiempo tiende a mejorar.")
        else:
            lineas.append("La presión se mantiene estable.")
    return "\n".join(lineas)


def _alertas_ejemplo_muestra():
    """Una alerta de ejemplo (solo para la muestra, no es real)."""
    return ["🌧️ <b>HOY: LLUVIA INTENSA</b>\n"
            "   💧 Acumulado: 22 mm\n"
            "   ☂️ No olvides paraguas"]


def _ejemplo_explicacion(alertas):
    """Ejemplo de explicación derivado de las alertas reales."""
    lineas = []
    for alerta in (alertas or []):
        texto = " ".join(str(alerta).split())
        if "LLUVIA" in texto:
            mm = re.search(r"Acumulado(?: esperado)?: (\d+) mm", texto)
            cantidad = f" de {mm.group(1)} mm" if mm else ""
            lineas.append(
                f"Lluvia intensa{cantidad}: lloverá mucho en poco "
                "tiempo, puede haber encharcamientos; evita cruzar "
                "arroyos y maneja con cuidado.")
        elif "FRENTE FRÍO" in texto:
            viento = re.search(r"Vientos: (\d+) km/h", texto)
            temp = re.search(r"Temperatura esperada: (\d+)°C", texto)
            linea = "Frente frío con viento norte"
            if viento:
                linea += f" de {viento.group(1)} km/h"
            if temp:
                linea += f" y {temp.group(1)} °C"
            lineas.append(linea + ": abrigarse bien y asegurar "
                          "objetos sueltos.")
        elif "CALOR" in texto:
            maxima = re.search(r"Máxima: (\d+)°C", texto)
            cantidad = f" de {maxima.group(1)} °C" if maxima else ""
            lineas.append(
                f"Calor extremo{cantidad}: hidratarse y evitar el sol "
                "de 11:00 a 16:00.")
        elif "VIENTOS" in texto:
            rafaga = re.search(r"Ráfagas: (\d+) km/h", texto)
            cantidad = f" de {rafaga.group(1)} km/h" if rafaga else ""
            lineas.append(
                f"Vientos muy fuertes con ráfagas{cantidad}: asegurar "
                "objetos sueltos y evitar estar bajo árboles.")
        elif "HELADA" in texto:
            minima = re.search(r"Mínima: ([\d.]+)", texto)
            cantidad = f" de {minima.group(1)} °C" if minima else ""
            lineas.append(
                f"Riesgo de helada con mínima{cantidad}: proteger "
                "plantas y mascotas.")
        elif "UV" in texto:
            uv = re.search(r"Índice UV: (\d+)", texto)
            cantidad = f" (índice {uv.group(1)})" if uv else ""
            lineas.append(
                f"Radiación UV extrema{cantidad}: usar protector solar, "
                "lentes y sombrero.")
        elif "BAJÓN" in texto:
            caida = re.search(r"Descenso: ([\d.]+)°C", texto)
            cantidad = f" de {caida.group(1)} °C" if caida else ""
            lineas.append(
                f"Bajón térmico{cantidad}: preparar ropa abrigadora.")
        else:
            limpio = re.sub(r"<[^>]*>", "", texto)
            lineas.append("Alerta vigente: "
                          + " ".join(limpio.split()) + ".")
    return "\n".join(lineas)


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
    os.environ.pop('GROQ_API_KEY', None)  # tampoco la del respaldo
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

    print("PASO 2c2: Narrativas nuevas SIN llave (sin red ni crash)...")
    try:
        dist_prueba = {
            'fecha': date(date.today().year, 12, 25),
            'distribucion': [('≤ 0°', 0), ('1–5°', 3), ('6–8°', 0),
                             ('9–10°', 16), ('11–12°', 16),
                             ('13–14°', 19), ('15–16°', 42),
                             ('17–18°', 3), ('19–20°', 0), ('≥ 21°', 0)],
            'mas_probable': ('15–16°', 42),
            'n_miembros': 31, 'prob_frio': 23, 'prob_muy_frio': 6,
            'prob_lluvia': 22,
        }
        sin_llave = [
            obtener_narrativa_dia(datos, ensemble=ensemble, api_key=None,
                                  groq_api_key=None),
            obtener_interpretacion_navidad(dist_prueba, api_key=None,
                                           groq_api_key=None),
            obtener_explicacion_alertas(_alertas_ejemplo_muestra(),
                                        api_key=None,
                                        groq_api_key=None),
        ]
    except Exception as e:
        errores.append(f"las narrativas sin llave lanzaron excepción: {e}")
        sin_llave = ["ERROR"]
        print(f"  ❌ FALLÓ (lanzó excepción: {e})")
    if sin_llave == [None, None, None]:
        print("  ✅ Las 3 devuelven None rápido, sin red ni crash")
    elif "ERROR" not in sin_llave:
        print("  ⚠️  Había llave en el entorno y alguna devolvió texto (no es error)")

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
        ejemplo_semana = _ejemplo_semana(datos)
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

    print("PASO 4e: Reporte de muestra con las narrativas de Gemini...")
    # Ejemplos (NO son salida de Gemini: solo muestran dónde queda
    # cada sección). La semana y la explicación se derivan de los
    # datos reales del día; la del día (ejemplo_dia) ya NO va en el
    # texto: vive solo en el caption de la tarjeta (PASO 4b).
    try:
        ejemplo_dia = _ejemplo_dia(datos, ensemble)
        ejemplo_semana = _ejemplo_semana(datos)
        alertas_muestra = alertas
        if not alertas_muestra:
            alertas_muestra = _alertas_ejemplo_muestra()
            print("  (sin alertas reales hoy: se usa una de ejemplo)")
        ejemplo_explicacion = _ejemplo_explicacion(alertas_muestra)
        mensaje_gemini = generar_mensaje_completo(
            datos, alertas_muestra, eventos, ensemble=ensemble,
            semana_narrativa=ejemplo_semana,
            explicacion_alertas=ejemplo_explicacion)
        ok = bool(mensaje_gemini)
        ok = ok and "LA SEMANA EN TEMPOAL" in mensaje_gemini
        if ejemplo_dia:
            ok = (ok and ejemplo_dia.splitlines()[0][:40]
                  not in mensaje_gemini)
        if ejemplo_explicacion:
            ok = (ok and ejemplo_explicacion.splitlines()[0][:40]
                  in mensaje_gemini)
        if ok:
            with open('reporte_muestra_gemini.txt', 'w',
                      encoding='utf-8') as f:
                f.write(mensaje_gemini)
            print("  ✅ Muestra guardada en reporte_muestra_gemini.txt")
        else:
            errores.append("la muestra Gemini no trae las secciones")
            print("  ❌ FALLÓ")
    except Exception as e:
        errores.append(f"no se pudo generar la muestra Gemini: {e}")
        print(f"  ❌ FALLÓ ({e})")

    print("PASO 4b: Generando tarjeta...")
    ruta_logo = os.path.join(os.path.dirname(__file__), '..', 'logo.png')
    ruta_tarjeta = generar_tarjeta_diaria(
        datos, 'tarjeta_prueba.png',
        ruta_logo=ruta_logo if os.path.exists(ruta_logo) else None,
        ensemble=ensemble)
    if ruta_tarjeta:
        # La narrativa diaria también va en el texto de la tarjeta
        # (mezclada con las viñetas); ejemplo_dia es el párrafo de
        # ejemplo del PASO 4e, derivado de los datos reales del día.
        narrativa_muestra = locals().get('ejemplo_dia')
        caption = generar_caption_tarjeta(
            datos, ensemble=ensemble, narrativa_dia=narrativa_muestra)
        print(f"  ✅ Tarjeta generada, caption {len(caption)} caracteres")
        if narrativa_muestra:
            if narrativa_muestra.splitlines()[0][:40] in caption:
                print("  ✅ Caption mezcla narrativa + viñetas")
            else:
                errores.append("el caption no trae la narrativa")
                print("  ❌ FALLÓ")
    else:
        errores.append("no se pudo generar la tarjeta")
        print("  ❌ FALLÓ")

    print("PASO 4c: Gráfica de Navidad (si es temporada)...")
    if temporada_navidad():
        ruta_navidad = None
        try:
            datos_gfs = obtener_datos_ensemble_navidad()
            if datos_gfs:
                dist = distribucion_minima_navidad(datos_gfs)
                if dist:
                    ruta_navidad = generar_grafica_navidad(
                        dist, 'grafica_navidad_prueba.png')
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

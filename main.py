#!/usr/bin/env python3
"""
Monitor Civil Tempoal
Sistema de Monitoreo Meteorológico Automatizado

Autor: Genaro Mateos Castro
Versión: 2.0.0
"""

import sys
import os

# Agregar src al path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from src.clima import (
    obtener_datos_climaticos,
    obtener_condiciones_actuales,
    obtener_datos_ensemble,
    obtener_datos_ensemble_navidad,
)
from src.alertas import analizar_riesgos_climaticos, detectar_eventos_especiales
from src.formato import (
    generar_caption_navidad,
    generar_caption_tarjeta,
    generar_mensaje_completo,
)
from src.narrador import (
    obtener_explicacion_alertas,
    obtener_interpretacion_navidad,
    obtener_narrativa_dia,
    obtener_narrativa_semanal,
)
from src.grafica_navidad import (
    calcular_probabilidades_frio,
    generar_grafica_navidad,
    rango_navidad,
    temporada_navidad,
)
from src.tarjeta import generar_tarjeta_diaria
from src.telegram_bot import enviar_mensaje_telegram, enviar_foto_telegram, validar_configuracion_telegram
from src.utils import logger

def main():
    """Función principal del sistema"""
    
    logger.info("=" * 60)
    logger.info("🚀 INICIANDO MONITOR CIVIL TEMPOAL v2.0")
    logger.info("=" * 60)
    
    # 1. Validar configuración
    logger.info("\n📋 PASO 1: Validando configuración...")
    if not validar_configuracion_telegram():
        logger.error("❌ Configuración inválida. Abortando.")
        logger.error("   Configura TELEGRAM_TOKEN y TELEGRAM_CHAT_ID en GitHub Secrets")
        sys.exit(1)
    
    # 2. Obtener datos meteorológicos
    logger.info("\n📋 PASO 2: Obteniendo datos meteorológicos...")
    datos = obtener_datos_climaticos(max_reintentos=3)
    
    if not datos:
        logger.error("❌ No se pudieron obtener datos meteorológicos")
        logger.error("   El sistema se detendrá sin enviar reporte")
        sys.exit(1)
    
    # 2b. Ensemble ECMWF (opcional, best-effort: si falla, el reporte
    # sigue con los datos deterministas y la heurística de confianza)
    logger.info("\n📋 PASO 2b: Obteniendo ensemble (probabilidades reales)...")
    ensemble = None
    try:
        ensemble = obtener_datos_ensemble()
        if ensemble:
            logger.info("✅ Ensemble ECMWF recibido")
        else:
            logger.warning("⚠️  Sin ensemble, se usará la heurística de confianza")
    except Exception as e:
        logger.warning(f"⚠️  Ensemble no disponible ({e}), se sigue sin él")

    # 2c. Narrativa semanal con Gemini (opcional, best-effort: sin llave
    # GEMINI_API_KEY o si la llamada falla, el reporte sigue sin la
    # sección semanal y nada se rompe)
    logger.info("\n📋 PASO 2c: Narrativa semanal (Gemini, opcional)...")
    semana_narrativa = None
    try:
        semana_narrativa = obtener_narrativa_semanal(
            datos['daily'], ensemble=ensemble)
        if semana_narrativa:
            logger.info("✅ Narrativa semanal lista")
        else:
            logger.info("   Sin narrativa semanal, el reporte sigue igual")
    except Exception as e:
        logger.warning(f"⚠️  Narrativa semanal no disponible ({e})")
        semana_narrativa = None

    # 2d. Narrativa del día con Gemini (opcional, best-effort: sin
    # llave GEMINI_API_KEY o si la llamada falla, el reporte sigue sin
    # la introducción y nada se rompe)
    logger.info("\n📋 PASO 2d: Narrativa del día (Gemini, opcional)...")
    narrativa_dia = None
    try:
        narrativa_dia = obtener_narrativa_dia(datos, ensemble=ensemble)
        if narrativa_dia:
            logger.info("✅ Narrativa del día lista")
        else:
            logger.info("   Sin narrativa del día, el reporte sigue igual")
    except Exception as e:
        logger.warning(f"⚠️  Narrativa del día no disponible ({e})")
        narrativa_dia = None

    # 3. Analizar riesgos
    logger.info("\n📋 PASO 3: Analizando riesgos meteorológicos...")
    alertas = analizar_riesgos_climaticos(datos['daily'])
    eventos = detectar_eventos_especiales(datos['hourly'])
    
    if alertas:
        logger.warning(f"⚠️  {len(alertas)} alertas detectadas")
    else:
        logger.info("✅ Sin alertas meteorológicas")
    
    if eventos:
        logger.warning(f"⚡ {len(eventos)} eventos especiales detectados")

    # 3b. Explicación de las alertas con Gemini (opcional, best-effort:
    # solo si hay alertas; si falla, el reporte sigue con las alertas
    # de siempre y nada se rompe)
    explicacion_alertas = None
    if alertas:
        logger.info("\n📋 PASO 3b: Explicación de alertas "
                    "(Gemini, opcional)...")
        try:
            explicacion_alertas = obtener_explicacion_alertas(alertas)
            if explicacion_alertas:
                logger.info("✅ Explicación de alertas lista")
            else:
                logger.info("   Sin explicación, el reporte sigue igual")
        except Exception as e:
            logger.warning(f"⚠️  Explicación no disponible ({e})")
            explicacion_alertas = None

    # 4. Generar mensaje
    logger.info("\n📋 PASO 4: Generando reporte...")
    mensaje = generar_mensaje_completo(datos, alertas, eventos,
                                        ensemble=ensemble,
                                        semana_narrativa=semana_narrativa,
                                        narrativa_dia=narrativa_dia,
                                        explicacion_alertas=explicacion_alertas)
    
    if not mensaje:
        logger.error("❌ Error generando mensaje")
        sys.exit(1)
    
    logger.info(f"✅ Reporte generado ({len(mensaje)} caracteres)")

    # 4b. Generar tarjeta diaria con imagen (no bloquea el reporte de texto)
    logger.info("\n📋 PASO 4b: Generando tarjeta diaria...")
    ruta_tarjeta = None
    caption_tarjeta = None
    try:
        ruta_logo = os.path.join(os.path.dirname(__file__), 'logo.png')
        ruta_tarjeta = generar_tarjeta_diaria(
            datos, "tarjeta_clima.png",
            ruta_logo=ruta_logo if os.path.exists(ruta_logo) else None,
            ensemble=ensemble)
        if ruta_tarjeta:
            # La narrativa diaria también va en el texto de la
            # tarjeta (mezclada con las viñetas); si Gemini falló,
            # el caption queda solo con las viñetas, como siempre.
            caption_tarjeta = generar_caption_tarjeta(
                datos, ensemble=ensemble, narrativa_dia=narrativa_dia)
        else:
            logger.warning("⚠️  No se pudo generar la tarjeta, se enviará solo texto")
    except Exception as e:
        logger.warning(f"⚠️  Error generando tarjeta (se enviará solo texto): {e}")
        ruta_tarjeta = None

    # 4c. Gráfica de Navidad (opcional, best-effort: solo en temporada
    # y solo si hay datos del ensemble GFS; nunca bloquea el reporte)
    logger.info("\n📋 PASO 4c: Gráfica de Navidad (si es temporada)...")
    ruta_navidad = None
    probs_navidad = None
    interpretacion_navidad = None
    if temporada_navidad():
        try:
            datos_gfs = obtener_datos_ensemble_navidad()
            if datos_gfs:
                rango = rango_navidad()
                if rango:
                    probs_navidad = calcular_probabilidades_frio(
                        datos_gfs, rango[0], rango[1])
                    if probs_navidad:
                        ruta_navidad = generar_grafica_navidad(
                            probs_navidad, "grafica_navidad.png")
            if not ruta_navidad:
                logger.warning("⚠️  Sin gráfica de Navidad, el reporte sigue igual")
        except Exception as e:
            logger.warning(f"⚠️  Gráfica de Navidad no disponible ({e})")
        # Interpretación de la gráfica con Gemini (opcional,
        # best-effort: solo si la gráfica salió; si falla, el caption
        # queda como siempre y nada se rompe)
        if probs_navidad:
            logger.info("\n📋 PASO 4c2: Interpretación de Navidad "
                        "(Gemini, opcional)...")
            try:
                interpretacion_navidad = obtener_interpretacion_navidad(
                    probs_navidad)
                if interpretacion_navidad:
                    logger.info("✅ Interpretación de Navidad lista")
                else:
                    logger.info("   Sin interpretación, el caption sigue igual")
            except Exception as e:
                logger.warning(f"⚠️  Interpretación no disponible ({e})")
                interpretacion_navidad = None
    else:
        logger.info("   Fuera de temporada, se omite")

    # 5. Enviar a Telegram: primero la tarjeta con sus conclusiones y
    # después el reporte de texto completo (la tarjeta es opcional: si
    # falla su envío, el reporte de texto sigue siendo el envío principal)
    logger.info("\n📋 PASO 5: Enviando reporte a Telegram...")
    if ruta_tarjeta:
        if not enviar_foto_telegram(ruta_tarjeta, caption_tarjeta):
            logger.warning("⚠️  No se pudo enviar la tarjeta, continúa el texto")
    if ruta_navidad:
        caption_navidad = generar_caption_navidad(
            probs_navidad, interpretacion=interpretacion_navidad)
        if not enviar_foto_telegram(ruta_navidad, caption_navidad):
            logger.warning("⚠️  No se pudo enviar la gráfica de Navidad")
    exito = enviar_mensaje_telegram(mensaje, max_reintentos=3)
    
    # 6. Resultado final
    logger.info("\n" + "=" * 60)
    if exito:
        logger.info("✅ PROCESO COMPLETADO EXITOSAMENTE")
        logger.info("=" * 60)
        sys.exit(0)
    else:
        logger.error("❌ EL REPORTE NO PUDO SER ENVIADO")
        logger.error("=" * 60)
        sys.exit(1)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.warning("\n⚠️  Proceso interrumpido por el usuario")
        sys.exit(130)
    except Exception as e:
        logger.error(f"\n❌ ERROR FATAL NO MANEJADO: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
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

from src.clima import obtener_datos_climaticos, obtener_condiciones_actuales
from src.alertas import analizar_riesgos_climaticos, detectar_eventos_especiales
from src.formato import generar_mensaje_completo
from src.telegram_bot import enviar_mensaje_telegram, validar_configuracion_telegram
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
    
    # 4. Generar mensaje
    logger.info("\n📋 PASO 4: Generando reporte...")
    mensaje = generar_mensaje_completo(datos, alertas, eventos)
    
    if not mensaje:
        logger.error("❌ Error generando mensaje")
        sys.exit(1)
    
    logger.info(f"✅ Reporte generado ({len(mensaje)} caracteres)")
    
    # 5. Enviar a Telegram
    logger.info("\n📋 PASO 5: Enviando reporte a Telegram...")
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
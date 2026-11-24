"""
Módulo de envío de mensajes a Telegram
"""

import requests
import os
from .utils import logger

def enviar_mensaje_telegram(mensaje, max_reintentos=3):
    """
    Envía mensaje a Telegram con reintentos automáticos
    
    Args:
        mensaje: Texto del mensaje en formato HTML
        max_reintentos: Número máximo de intentos
        
    Returns:
        bool: True si se envió exitosamente, False si falló
    """
    
    token = os.environ.get('TELEGRAM_TOKEN')
    chat_id = os.environ.get('TELEGRAM_CHAT_ID')
    
    if not token:
        logger.error("❌ TELEGRAM_TOKEN no está configurado")
        return False
    
    if not chat_id:
        logger.error("❌ TELEGRAM_CHAT_ID no está configurado")
        return False
    
    logger.info(f"📤 Enviando reporte a {chat_id}...")
    
    url = f"https://api.telegram.org/bot{token.strip()}/sendMessage"
    
    payload = {
        "chat_id": chat_id,
        "text": mensaje,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }
    
    for intento in range(1, max_reintentos + 1):
        try:
            logger.info(f"📨 Intento {intento}/{max_reintentos}...")
            
            response = requests.post(url, data=payload, timeout=20)
            
            if response.status_code == 200:
                logger.info("✅ ¡MENSAJE ENVIADO EXITOSAMENTE!")
                result = response.json()
                if result.get('ok'):
                    logger.info(f"   📊 Message ID: {result['result']['message_id']}")
                return True
            
            elif response.status_code == 400:
                logger.error(f"❌ Error 400 - Solicitud inválida:")
                logger.error(f"   {response.text}")
                # No reintentar en errores 400 (problema con el mensaje)
                return False
            
            elif response.status_code == 401:
                logger.error(f"❌ Error 401 - Token inválido")
                logger.error("   Verifica TELEGRAM_TOKEN en GitHub Secrets")
                return False
            
            elif response.status_code == 404:
                logger.error(f"❌ Error 404 - Chat no encontrado")
                logger.error(f"   Verifica TELEGRAM_CHAT_ID: {chat_id}")
                return False
            
            else:
                logger.warning(f"⚠️  Error {response.status_code}: {response.text}")
                if intento < max_reintentos:
                    import time
                    time.sleep(3)
        
        except requests.Timeout:
            logger.warning(f"⏱️  Timeout en intento {intento}")
            if intento < max_reintentos:
                import time
                time.sleep(3)
        
        except requests.RequestException as e:
            logger.error(f"❌ Error de conexión: {e}")
            if intento < max_reintentos:
                import time
                time.sleep(3)
        
        except Exception as e:
            logger.error(f"❌ Error inesperado: {e}")
            if intento < max_reintentos:
                import time
                time.sleep(3)
    
    logger.error("❌ Todos los intentos de envío fallaron")
    return False

def enviar_foto_telegram(ruta_imagen, caption=None, max_reintentos=3):
    """
    Envía una foto a Telegram con reintentos automáticos.

    Args:
        ruta_imagen: Ruta del archivo de imagen a enviar.
        caption: Texto opcional que acompaña la foto (máx. 1024 caracteres).
        max_reintentos: Número máximo de intentos.

    Returns:
        bool: True si se envió exitosamente, False si falló.
    """
    token = os.environ.get('TELEGRAM_TOKEN')
    chat_id = os.environ.get('TELEGRAM_CHAT_ID')

    if not token:
        logger.error("❌ TELEGRAM_TOKEN no está configurado")
        return False

    if not chat_id:
        logger.error("❌ TELEGRAM_CHAT_ID no está configurado")
        return False

    if not ruta_imagen or not os.path.exists(ruta_imagen):
        logger.error(f"❌ Imagen no encontrada: {ruta_imagen}")
        return False

    logger.info(f"📤 Enviando foto a {chat_id}...")

    url = f"https://api.telegram.org/bot{token.strip()}/sendPhoto"

    payload = {
        "chat_id": chat_id,
        "parse_mode": "HTML",
    }
    if caption:
        # Telegram limita el caption a 1024 caracteres
        payload["caption"] = caption[:1024]

    for intento in range(1, max_reintentos + 1):
        try:
            logger.info(f"🖼️  Intento {intento}/{max_reintentos}...")

            with open(ruta_imagen, 'rb') as foto:
                files = {"photo": foto}
                response = requests.post(url, data=payload, files=files,
                                         timeout=30)

            if response.status_code == 200:
                logger.info("✅ ¡FOTO ENVIADA EXITOSAMENTE!")
                result = response.json()
                if result.get('ok'):
                    logger.info(f"   📊 Message ID: {result['result']['message_id']}")
                return True

            elif response.status_code in (400, 401, 404):
                logger.error(f"❌ Error {response.status_code} enviando foto:")
                logger.error(f"   {response.text}")
                # No reintentar: problema con la solicitud o el token/chat
                return False

            else:
                logger.warning(f"⚠️  Error {response.status_code}: {response.text}")
                if intento < max_reintentos:
                    import time
                    time.sleep(3)

        except requests.Timeout:
            logger.warning(f"⏱️  Timeout en intento {intento}")
            if intento < max_reintentos:
                import time
                time.sleep(3)

        except requests.RequestException as e:
            logger.error(f"❌ Error de conexión: {e}")
            if intento < max_reintentos:
                import time
                time.sleep(3)

        except Exception as e:
            logger.error(f"❌ Error inesperado: {e}")
            if intento < max_reintentos:
                import time
                time.sleep(3)

    logger.error("❌ Todos los intentos de envío de foto fallaron")
    return False

def validar_configuracion_telegram():
    """
    Valida que las variables de entorno de Telegram estén configuradas
    """
    token = os.environ.get('TELEGRAM_TOKEN')
    chat_id = os.environ.get('TELEGRAM_CHAT_ID')
    
    errores = []
    
    if not token:
        errores.append("TELEGRAM_TOKEN no está configurado")
    elif len(token.strip()) < 40:
        errores.append("TELEGRAM_TOKEN parece inválido (muy corto)")
    
    if not chat_id:
        errores.append("TELEGRAM_CHAT_ID no está configurado")
    
    if errores:
        for error in errores:
            logger.error(f"❌ {error}")
        return False
    
    logger.info("✅ Configuración de Telegram válida")
    return True
"""
Utilidades generales del sistema
"""

import logging
import sys
from datetime import datetime
import pytz

# Configuración de logging
def configurar_logging():
    """Configura el sistema de logging"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout)
        ]
    )
    return logging.getLogger(__name__)

logger = configurar_logging()

# Constantes
DIAS_ESP = {
    "Monday": "LUNES",
    "Tuesday": "MARTES",
    "Wednesday": "MIÉRCOLES",
    "Thursday": "JUEVES",
    "Friday": "VIERNES",
    "Saturday": "SÁBADO",
    "Sunday": "DOMINGO"
}

MESES_ESP = {
    1: "Enero", 2: "Febrero", 3: "Marzo", 4: "Abril",
    5: "Mayo", 6: "Junio", 7: "Julio", 8: "Agosto",
    9: "Septiembre", 10: "Octubre", 11: "Noviembre", 12: "Diciembre"
}

def obtener_hora_mexico():
    """Obtiene la hora actual en zona horaria de México"""
    tz_mexico = pytz.timezone('America/Mexico_City')
    return datetime.now(tz_mexico)

def formatear_fecha_completa():
    """Formatea la fecha en español completo"""
    ahora = obtener_hora_mexico()
    dia_semana = DIAS_ESP[ahora.strftime("%A")]
    dia = ahora.day
    mes = MESES_ESP[ahora.month]
    año = ahora.year
    hora = ahora.strftime("%H:%M")
    
    return f"{dia_semana} {dia} de {mes} de {año} - {hora}"

def validar_datos_api(data, campos_requeridos):
    """Valida que la respuesta de la API tenga los campos necesarios"""
    if not data:
        logger.error("Datos vacíos recibidos")
        return False
    
    for campo in campos_requeridos:
        if campo not in data:
            logger.error(f"Campo requerido '{campo}' no encontrado en datos")
            return False
    
    return True
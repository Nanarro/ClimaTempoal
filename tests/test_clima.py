"""
Tests unitarios para el sistema de monitoreo
"""

import unittest
import sys
import os

# Agregar src al path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from src.utils import DIAS_ESP, MESES_ESP
from src.alertas import analizar_riesgos_climaticos
from src.formato import obtener_icono_clima

class TestUtils(unittest.TestCase):
    """Tests para utilidades"""
    
    def test_dias_espanol(self):
        """Verifica traducción de días"""
        self.assertEqual(DIAS_ESP["Monday"], "LUNES")
        self.assertEqual(DIAS_ESP["Friday"], "VIERNES")
        self.assertEqual(len(DIAS_ESP), 7)
    
    def test_meses_espanol(self):
        """Verifica traducción de meses"""
        self.assertEqual(MESES_ESP[1], "Enero")
        self.assertEqual(MESES_ESP[12], "Diciembre")
        self.assertEqual(len(MESES_ESP), 12)

class TestAlertas(unittest.TestCase):
    """Tests para sistema de alertas"""
    
    def test_analizar_riesgos_sin_datos(self):
        """Verifica comportamiento con datos vacíos"""
        daily = {
            'temperature_2m_max': [],
            'temperature_2m_min': [],
            'time': [],
            'wind_direction_10m_dominant': [],
            'wind_gusts_10m_max': [],
            'precipitation_sum': [],
            'uv_index_max': []
        }
        resultado = analizar_riesgos_climaticos(daily)
        self.assertEqual(resultado, [])
    
    def test_analizar_riesgos_datos_insuficientes(self):
        """Verifica comportamiento con un solo día"""
        daily = {
            'temperature_2m_max': [25],
            'temperature_2m_min': [15],
            'time': ['2026-01-20'],
            'wind_direction_10m_dominant': [180],
            'wind_gusts_10m_max': [20],
            'precipitation_sum': [0],
            'uv_index_max': [5]
        }
        resultado = analizar_riesgos_climaticos(daily)
        self.assertEqual(resultado, [])

class TestFormato(unittest.TestCase):
    """Tests para formateo de mensajes"""
    
    def test_icono_clima_despejado(self):
        """Verifica icono para día despejado"""
        self.assertEqual(obtener_icono_clima(0), "☀️")
    
    def test_icono_clima_lluvia(self):
        """Verifica icono para lluvia"""
        self.assertEqual(obtener_icono_clima(61), "🌧️")
    
    def test_icono_clima_tormenta(self):
        """Verifica icono para tormenta"""
        self.assertEqual(obtener_icono_clima(95), "⛈️")
    
    def test_icono_clima_desconocido(self):
        """Verifica icono para código desconocido"""
        self.assertEqual(obtener_icono_clima(9999), "🌡️")

if __name__ == '__main__':
    unittest.main()
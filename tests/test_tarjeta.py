"""
Tests unitarios para la tarjeta diaria de pronóstico (imagen).
"""

import os
import sys
import unittest

# Agregar src al path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from src.formato import (
    direccion_viento_texto,
    etiqueta_bloque,
    generar_caption_tarjeta,
    generar_conclusiones_bloques,
    nivel_confianza,
    obtener_bloques_diarios,
)
from src.tarjeta import generar_tarjeta_diaria


def _datos_ejemplo():
    """Datos sintéticos con el formato de Open-Meteo para un día de norte."""
    horas = []
    temps = []
    sens = []
    probs = []
    lluvias = []
    vientos = []
    rafagas = []
    dirs = []
    presiones = []
    nubes = []
    codigos = []
    for h in range(24):
        horas.append(f"2026-11-24T{h:02d}:00")
        temps.append(17.0 + 0.2 * h if h < 12 else 21.0 - 0.3 * (h - 12))
        sens.append(temps[-1] - 1.0)
        probs.append(80 if h < 12 else (60 if h < 18 else 40))
        lluvias.append(0.5 if h < 12 else 0.1)
        vientos.append(12.0 + h * 0.8)
        rafagas.append(vientos[-1] * 1.5)
        dirs.append(350.0)  # Viento del norte
        presiones.append(1019.0 + h * 0.1)
        nubes.append(90 if h < 12 else 60)
        codigos.append(61 if h < 12 else 3)
    return {
        'hourly': {
            'time': horas,
            'temperature_2m': temps,
            'apparent_temperature': sens,
            'precipitation_probability': probs,
            'precipitation': lluvias,
            'weather_code': codigos,
            'wind_speed_10m': vientos,
            'wind_gusts_10m': rafagas,
            'wind_direction_10m': dirs,
            'surface_pressure': presiones,
            'cloud_cover': nubes,
        },
        'daily': {
            'time': ['2026-11-24'],
            'temperature_2m_max': [21.0],
            'temperature_2m_min': [16.0],
            'precipitation_probability_max': [80],
            'precipitation_sum': [5.0],
            'wind_speed_10m_max': [30.0],
            'wind_direction_10m_dominant': [350.0],
            'weather_code': [61],
        },
        'current': {
            'temperature_2m': 17.0,
            'apparent_temperature': 16.0,
            'relative_humidity_2m': 85,
            'weather_code': 61,
            'wind_speed_10m': 15.0,
        },
    }


class TestBloquesDiarios(unittest.TestCase):
    """Tests para el resumen de bloques mañana/tarde/noche."""

    def test_tres_bloques(self):
        bloques = obtener_bloques_diarios(_datos_ejemplo())
        self.assertEqual(len(bloques), 3)
        self.assertEqual([b['nombre'] for b in bloques],
                         ["MAÑANA", "TARDE", "NOCHE"])

    def test_bloque_manana_lluvioso(self):
        bloques = obtener_bloques_diarios(_datos_ejemplo())
        manana = bloques[0]
        self.assertEqual(manana['prob_max'], 80)
        self.assertEqual(manana['viento_dir'], "NORTE")
        self.assertIsNotNone(manana['presion_media'])
        self.assertGreater(manana['presion_media'], 1000)

    def test_direccion_viento(self):
        self.assertEqual(direccion_viento_texto(0), "NORTE")
        self.assertEqual(direccion_viento_texto(350), "NORTE")
        self.assertEqual(direccion_viento_texto(90), "ESTE")
        self.assertEqual(direccion_viento_texto(180), "SUR")
        self.assertEqual(direccion_viento_texto(270), "OESTE")

    def test_etiqueta_bloque(self):
        bloques = obtener_bloques_diarios(_datos_ejemplo())
        self.assertIn(etiqueta_bloque(bloques[0]), ("LLUVIAS", "POSIBLES LLUVIAS"))

    def test_nivel_confianza(self):
        bloques = obtener_bloques_diarios(_datos_ejemplo())
        nivel, segmentos = nivel_confianza(bloques)
        self.assertIn(nivel, ("BAJA", "MEDIA", "ALTA"))
        self.assertTrue(1 <= segmentos <= 4)


class TestConclusiones(unittest.TestCase):
    """Tests para las conclusiones narradas por bloque."""

    def test_tres_conclusiones(self):
        conclusiones = generar_conclusiones_bloques(_datos_ejemplo())
        self.assertEqual(len(conclusiones), 3)
        for texto in conclusiones:
            self.assertIn("•", texto)

    def test_caption_corto(self):
        caption = generar_caption_tarjeta(_datos_ejemplo())
        self.assertTrue(len(caption) > 0)
        # Límite de Telegram para captions: 1024 caracteres
        self.assertLessEqual(len(caption), 1024)


class TestTarjetaImagen(unittest.TestCase):
    """Tests para la generación de la imagen de la tarjeta."""

    def test_genera_png(self):
        ruta = "/tmp/tarjeta_test.png"
        if os.path.exists(ruta):
            os.remove(ruta)
        resultado = generar_tarjeta_diaria(_datos_ejemplo(), ruta)
        self.assertEqual(resultado, ruta)
        self.assertTrue(os.path.exists(ruta))
        self.assertGreater(os.path.getsize(ruta), 10000)
        from PIL import Image
        with Image.open(ruta) as img:
            self.assertEqual(img.size, (1200, 800))
            self.assertEqual(img.format, "PNG")
        os.remove(ruta)


if __name__ == '__main__':
    unittest.main()

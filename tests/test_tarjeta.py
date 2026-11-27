"""
Tests unitarios para la tarjeta diaria de pronóstico (imagen).
"""

import os
import sys
import unittest
from datetime import date

from PIL import Image, ImageDraw

# Agregar src al path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import src.tarjeta as tarjeta_mod
from src.formato import (
    direccion_viento_texto,
    etiqueta_bloque,
    generar_caption_tarjeta,
    generar_conclusiones_bloques,
    nivel_confianza,
    obtener_bloques_diarios,
)
from src.tarjeta import (
    DIR_FONDOS,
    _dibujar_esferas_navidad,
    generar_tarjeta_diaria,
    seleccionar_fondo,
    texto_cuenta_regresiva,
)


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
            'time': ['2026-11-24', '2026-11-25', '2026-11-26', '2026-11-27',
                     '2026-11-28', '2026-11-29', '2026-11-30'],
            'temperature_2m_max': [21.0, 22.0, 23.0, 22.0, 21.0, 20.0, 20.0],
            'temperature_2m_min': [16.0, 15.0, 16.0, 15.0, 14.0, 14.0, 13.0],
            'apparent_temperature_max': [20.0, 21.0, 22.0, 21.0, 20.0, 19.0, 19.0],
            'apparent_temperature_min': [15.0, 14.0, 15.0, 14.0, 13.0, 13.0, 12.0],
            'sunrise': ['2026-11-24T06:30', '2026-11-25T06:31',
                        '2026-11-26T06:31', '2026-11-27T06:32',
                        '2026-11-28T06:32', '2026-11-29T06:33',
                        '2026-11-30T06:33'],
            'sunset': ['2026-11-24T17:45', '2026-11-25T17:45',
                       '2026-11-26T17:45', '2026-11-27T17:45',
                       '2026-11-28T17:44', '2026-11-29T17:44',
                       '2026-11-30T17:44'],
            'uv_index_max': [5.0, 6.0, 6.0, 5.0, 5.0, 4.0, 4.0],
            'precipitation_probability_max': [80, 60, 40, 30, 20, 10, 10],
            'precipitation_sum': [5.0, 3.0, 1.0, 0.5, 0.0, 0.0, 0.0],
            'wind_speed_10m_max': [30.0, 25.0, 20.0, 18.0, 15.0, 12.0, 12.0],
            'wind_gusts_10m_max': [45.0, 38.0, 30.0, 27.0, 22.0, 18.0, 18.0],
            'wind_direction_10m_dominant': [350.0, 340.0, 20.0, 45.0, 90.0, 90.0, 90.0],
            'weather_code': [61, 61, 3, 2, 1, 0, 0],
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
                         ["POR LA MAÑANA", "TARDE", "NOCHE"])

    def test_conclusion_manana_dice_por_la_manana(self):
        """La viñeta de la mañana dice 'POR LA MAÑANA', no 'MAÑANA':
        'mañana' sola se confunde con el día siguiente."""
        conclusiones = generar_conclusiones_bloques(_datos_ejemplo())
        self.assertEqual(len(conclusiones), 3)
        self.assertIn("<b>POR LA MAÑANA (06–12 h):</b>",
                      conclusiones[0])

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


def _bloque_base(**cambios):
    """Bloque sintético con valores por defecto (día despejado)."""
    bloque = {
        'nombre': 'POR LA MAÑANA',
        'codigo': 0,
        'prob_max': 0,
        'temp_max': 25.0,
        'temp_media': 24.0,
        'viento_max': 10.0,
        'nubosidad_media': 30,
        'lluvia_7d': 5.0,
    }
    bloque.update(cambios)
    return bloque


class TestFondos(unittest.TestCase):
    """Tests para la selección de la foto de fondo por condición."""

    def test_todas_las_fotos_existen(self):
        esperadas = {
            'despejado.jpg', 'soleado.jpg', 'nublado.jpg', 'chubascos.jpg',
            'tormenta.jpg', 'viento.jpg', 'calor.jpg', 'calor_extremo.jpg',
            'sequia.jpg', 'frente_frio.jpg', 'noche_despejado.jpg',
            'noche_nublado.jpg', 'noche_chubascos.jpg', 'noche_tormenta.jpg',
            'noche_frente_frio.jpg',
        }
        presentes = set(os.listdir(DIR_FONDOS))
        self.assertTrue(esperadas <= presentes,
                        f"Faltan fotos: {esperadas - presentes}")

    def test_condiciones_dia(self):
        casos = [
            ({}, 'despejado.jpg'),
            ({'codigo': 95}, 'tormenta.jpg'),
            ({'viento_max': 55.0}, 'frente_frio.jpg'),
            ({'temp_max': 41.0}, 'calor_extremo.jpg'),
            ({'prob_max': 80}, 'chubascos.jpg'),
            ({'lluvia_7d': 0.5, 'temp_max': 34.0}, 'sequia.jpg'),
            ({'temp_max': 36.0}, 'calor.jpg'),
            ({'viento_max': 35.0}, 'viento.jpg'),
            ({'nubosidad_media': 90}, 'nublado.jpg'),
            ({'temp_media': 29.0, 'nubosidad_media': 20}, 'soleado.jpg'),
        ]
        for cambios, esperado in casos:
            with self.subTest(cambios=cambios):
                ruta = seleccionar_fondo(_bloque_base(**cambios))
                self.assertIsNotNone(ruta, f"sin foto para {cambios}")
                self.assertTrue(ruta.endswith(esperado), ruta)

    def test_variantes_noche(self):
        casos = [
            ({}, 'noche_despejado.jpg'),
            ({'prob_max': 80}, 'noche_chubascos.jpg'),
            ({'codigo': 95}, 'noche_tormenta.jpg'),
            ({'viento_max': 55.0}, 'noche_frente_frio.jpg'),
            ({'temp_max': 36.0}, 'noche_despejado.jpg'),
        ]
        for cambios, esperado in casos:
            with self.subTest(cambios=cambios):
                bloque = _bloque_base(nombre='NOCHE', **cambios)
                ruta = seleccionar_fondo(bloque)
                self.assertIsNotNone(ruta, f"sin foto para {cambios}")
                self.assertTrue(ruta.endswith(esperado), ruta)

    def test_sin_foto_no_falla(self):
        original = tarjeta_mod.DIR_FONDOS
        tarjeta_mod.DIR_FONDOS = "/tmp/no-existe-fondos"
        try:
            self.assertIsNone(seleccionar_fondo(_bloque_base()))
        finally:
            tarjeta_mod.DIR_FONDOS = original


class TestCuentaRegresiva(unittest.TestCase):
    """Tests para el contador de días a festividades."""

    def test_fechas(self):
        casos = [
            (date(2026, 10, 15), "Faltan 16 días para Halloween"),
            (date(2026, 10, 31), "¡Hoy es Halloween!"),
            (date(2026, 10, 2), "Faltan 29 días para Halloween"),
            (date(2026, 11, 1), "Hoy es Día de Muertos"),
            (date(2026, 11, 2), "Hoy es Día de Muertos"),
            (date(2026, 12, 10), "Faltan 15 días para Navidad"),
            (date(2026, 12, 25), "¡Hoy es Navidad!"),
            (date(2026, 12, 28), "Faltan 4 días para Año Nuevo"),
            (date(2027, 1, 1), "¡Hoy es Año Nuevo!"),
            (date(2026, 12, 24), "Falta 1 día para Navidad"),
        ]
        for fecha, esperado in casos:
            with self.subTest(fecha=fecha):
                self.assertEqual(texto_cuenta_regresiva(fecha), esperado)

    def test_fuera_de_temporada(self):
        self.assertIsNone(texto_cuenta_regresiva(date(2026, 6, 15)))
        self.assertIsNone(texto_cuenta_regresiva(date(2026, 11, 24)))
        self.assertIsNone(texto_cuenta_regresiva(date(2026, 9, 30)))


class TestMensajeCompleto(unittest.TestCase):
    """El reporte de texto no debe morir por un campo opcional faltante."""

    def test_con_amanecer(self):
        from src.formato import generar_mensaje_completo
        mensaje = generar_mensaje_completo(_datos_ejemplo(), [], [])
        self.assertIsNotNone(mensaje)
        self.assertIn("Amanecer: 06:30", mensaje)
        self.assertIn("MONITOREO PROTECCIÓN CIVIL TEMPOAL", mensaje)

    def test_sin_amanecer_sigue_generando(self):
        # Regresión: antes, si faltaban sunrise/sunset, todo el reporte
        # fallaba y main.py terminaba sin enviar nada
        from src.formato import generar_mensaje_completo
        datos = _datos_ejemplo()
        del datos['daily']['sunrise']
        del datos['daily']['sunset']
        mensaje = generar_mensaje_completo(datos, [], [])
        self.assertIsNotNone(mensaje)
        self.assertNotIn("Amanecer:", mensaje)
        self.assertIn("MONITOREO PROTECCIÓN CIVIL TEMPOAL", mensaje)

    def test_trae_resumen_ejecutivo_y_horario(self):
        # El texto trae el resumen ejecutivo de siempre: condiciones
        # actuales con viento, pronóstico horario con las temperaturas
        # y el viento a lo largo del día, próximos 3 días y
        # estadísticas de la semana, más el resumen decisivo del día.
        from src.formato import generar_mensaje_completo
        mensaje = generar_mensaje_completo(_datos_ejemplo(), [], [])
        self.assertIsNotNone(mensaje)
        for seccion in ("RESUMEN EJECUTIVO", "CONDICIONES ACTUALES",
                        "PRONÓSTICO HORARIO", "PRÓXIMOS 3 DÍAS",
                        "ESTADÍSTICAS SEMANALES", "Hoy en Tempoal:"):
            self.assertIn(seccion, mensaje)
        self.assertIn("Viento:", mensaje)

    def test_no_repite_los_bloques_del_caption(self):
        # Los 3 bloques ya van en el caption de la tarjeta; el texto
        # no los repite (antes el canal mostraba lo mismo dos veces).
        from src.formato import generar_mensaje_completo
        mensaje = generar_mensaje_completo(_datos_ejemplo(), [], [])
        self.assertIsNotNone(mensaje)
        for vineta in ("POR LA MAÑANA (06–12 h):",
                       "TARDE (12–18 h):", "NOCHE (18–00 h):"):
            self.assertNotIn(vineta, mensaje)


class TestDecoracionDiciembre(unittest.TestCase):
    """La decoración navideña se dibuja sin errores."""

    def test_esferas(self):
        img = Image.new("RGB", (1200, 800), (11, 21, 38))
        draw = ImageDraw.Draw(img)
        _dibujar_esferas_navidad(draw)  # No debe lanzar excepciones


if __name__ == '__main__':
    unittest.main()

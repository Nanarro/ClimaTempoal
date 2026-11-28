"""
Tests unitarios para la integración del Ensemble de Open-Meteo
(ECMWF para la tarjeta diaria, GFS para la gráfica de Navidad).
"""

import os
import sys
import unittest
from datetime import date
from unittest.mock import MagicMock, patch

import requests

# Agregar src al path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from src.clima import (
    obtener_datos_ensemble,
    obtener_datos_ensemble_navidad,
)
from src.formato import (
    extraer_ensemble_bloque,
    generar_caption_tarjeta,
    nivel_confianza,
    obtener_bloques_diarios,
)
from src.grafica_navidad import (
    distribucion_minima_navidad,
    generar_grafica_navidad,
    temporada_navidad,
)
from src.tarjeta import generar_tarjeta_diaria

FECHA = "2026-11-24"


def _datos_det():
    """Datos deterministas sintéticos (día de norte, como test_tarjeta)."""
    horas, temps, sens, probs = [], [], [], []
    lluvias, vientos, rafagas, dirs = [], [], [], []
    presiones, nubes, codigos = [], [], []
    for h in range(24):
        horas.append(f"{FECHA}T{h:02d}:00")
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
    return {
        'hourly': {
            'time': horas, 'temperature_2m': temps,
            'apparent_temperature': sens,
            'precipitation_probability': probs, 'precipitation': lluvias,
            'weather_code': codigos, 'wind_speed_10m': vientos,
            'wind_gusts_10m': rafagas, 'wind_direction_10m': dirs,
            'surface_pressure': presiones, 'cloud_cover': nubes,
        },
        'daily': {
            'time': [FECHA, '2026-11-25', '2026-11-26', '2026-11-27',
                     '2026-11-28', '2026-11-29', '2026-11-30'],
            'temperature_2m_max': [21.0, 22.0, 23.0, 22.0, 21.0, 20.0, 20.0],
            'temperature_2m_min': [16.0, 15.0, 16.0, 15.0, 14.0, 14.0, 13.0],
            'apparent_temperature_max': [20.0, 21.0, 22.0, 21.0, 20.0, 19.0, 19.0],
            'apparent_temperature_min': [15.0, 14.0, 15.0, 14.0, 13.0, 13.0, 12.0],
            'sunrise': [f"{FECHA}T06:30", '2026-11-25T06:31',
                        '2026-11-26T06:31', '2026-11-27T06:32',
                        '2026-11-28T06:32', '2026-11-29T06:33',
                        '2026-11-30T06:33'],
            'sunset': [f"{FECHA}T17:45", '2026-11-25T17:45',
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
            'temperature_2m': 17.0, 'apparent_temperature': 16.0,
            'relative_humidity_2m': 85, 'weather_code': 61,
            'wind_speed_10m': 15.0,
        },
    }


def _ensemble_ejemplo():
    """
    Ensemble ECMWF sintético de 5 miembros para FECHA.
    Temperatura: base(h) + offset [-2,-1,0,1,2] por miembro.
    Lluvia: en la mañana llueven los miembros 1-3 (3/5 = 60%),
    en la tarde solo el miembro 1 (1/5 = 20%), en la noche ninguno.
    """
    horas = [f"{FECHA}T{h:02d}:00" for h in range(24)]
    hourly = {'time': horas}
    offsets = [-2.0, -1.0, 0.0, 1.0, 2.0]
    for m, off in enumerate(offsets, start=1):
        temps = []
        precs = []
        for h in range(24):
            base = 17.0 + 0.2 * h if h < 12 else 21.0 - 0.3 * (h - 12)
            temps.append(round(base + off, 1))
            if h < 12:
                precs.append(0.5 if m <= 3 else 0.0)
            elif h < 18:
                precs.append(0.2 if m == 1 else 0.0)
            else:
                precs.append(0.0)
        hourly[f'temperature_2m_member{m:02d}'] = temps
        hourly[f'precipitation_member{m:02d}'] = precs
    return {'hourly': hourly}


def _gfs_ejemplo():
    """Ensemble GFS sintético: 3 miembros, 5 días, mínimas diarias."""
    return {
        'daily': {
            'time': ['2026-11-26', '2026-11-27', '2026-11-28',
                     '2026-11-29', '2026-11-30'],
            'temperature_2m_min_member01': [11.0, 13.0, 9.0, 12.5, 15.0],
            'temperature_2m_min_member02': [12.5, 11.5, 10.5, 13.0, 14.0],
            'temperature_2m_min_member03': [13.0, 12.0, 11.0, 11.0, 16.0],
        }
    }


def _gfs_navidad_ejemplo():
    """Ensemble GFS sintético para la distribución del 25 de diciembre.

    24–26 dic, 3 miembros + control. El 25 dic las mínimas son
    15.5, 9.5, 4.4 (miembros) y 16.2 (control): 15–16 °C: 2/4 (50%),
    9–10 °C: 1/4 (25%), 1–5 °C: 1/4 (25%); frío (<12): 2/4 (50%),
    muy frío (<10): 2/4 (50%). Lluvia ese día: 0.5, 0.0, 0.0, 0.3
    mm (control): 2/4 con >0.1 mm (50%).
    """
    return {
        'daily': {
            'time': ['2026-12-24', '2026-12-25', '2026-12-26'],
            'temperature_2m_min': [13.0, 16.2, 11.0],
            'temperature_2m_min_member01': [16.0, 15.5, 14.0],
            'temperature_2m_min_member02': [10.0, 9.5, 12.0],
            'temperature_2m_min_member03': [21.0, 4.4, 0.0],
            'precipitation_sum': [0.0, 0.5, 0.0],
            'precipitation_sum_member01': [0.0, 0.0, 0.0],
            'precipitation_sum_member02': [0.2, 0.0, 0.0],
            'precipitation_sum_member03': [0.0, 0.3, 0.0],
        }
    }


def _bloques_ens(spreads, probs):
    """Bloques sintéticos con estadísticas de ensemble."""
    return [
        {'nombre': n, 'temp_spread': s, 'prob_lluvia_ens': p}
        for n, s, p in zip(("POR LA MAÑANA", "TARDE", "NOCHE"), spreads, probs)
    ]


class TestEnsembleBloque(unittest.TestCase):
    """Probabilidad real de lluvia y dispersión por bloque."""

    def test_prob_lluvia_manana_60(self):
        ens = extraer_ensemble_bloque(_ensemble_ejemplo(), 6, 12, FECHA)
        self.assertIsNotNone(ens)
        self.assertEqual(ens['prob_lluvia_ens'], 60)  # 3 de 5 miembros
        self.assertEqual(ens['n_miembros'], 5)

    def test_prob_lluvia_tarde_20_noche_0(self):
        ens_tarde = extraer_ensemble_bloque(_ensemble_ejemplo(), 12, 18, FECHA)
        ens_noche = extraer_ensemble_bloque(_ensemble_ejemplo(), 18, 24, FECHA)
        self.assertEqual(ens_tarde['prob_lluvia_ens'], 20)  # 1 de 5
        self.assertEqual(ens_noche['prob_lluvia_ens'], 0)

    def test_temp_media_y_spread(self):
        # Mañana: medias de miembro 16.7, 17.7, 18.7, 19.7, 20.7
        ens = extraer_ensemble_bloque(_ensemble_ejemplo(), 6, 12, FECHA)
        self.assertAlmostEqual(ens['temp_media_ens'], 18.7, places=1)
        # Desviación estándar poblacional de [-2,-1,0,1,2] = sqrt(2) ≈ 1.4
        self.assertAlmostEqual(ens['temp_spread'], 1.4, places=1)

    def test_sin_miembros_devuelve_none(self):
        self.assertIsNone(
            extraer_ensemble_bloque({'hourly': {'time': []}}, 6, 12, FECHA))
        self.assertIsNone(extraer_ensemble_bloque(None, 6, 12, FECHA))

    def test_sin_horas_en_bloque_devuelve_none(self):
        # Ensemble de otra fecha: ningún índice cae en el bloque
        ens = extraer_ensemble_bloque(_ensemble_ejemplo(), 6, 12, "2026-11-30")
        self.assertIsNone(ens)


class TestNivelConfianzaEnsemble(unittest.TestCase):
    """La confianza real se calcula del acuerdo entre miembros."""

    def test_alta_acuerdo_estrecho(self):
        nivel, seg = nivel_confianza(_bloques_ens([1.0, 1.2, 0.8], [0, 10, 0]))
        self.assertEqual((nivel, seg), ("ALTA", 4))

    def test_baja_por_dispersion(self):
        nivel, seg = nivel_confianza(_bloques_ens([3.5, 3.0, 3.2], [0, 0, 0]))
        self.assertEqual((nivel, seg), ("BAJA", 2))

    def test_baja_por_desacuerdo_lluvia(self):
        # 50% en un bloque = casi un volado
        nivel, seg = nivel_confianza(_bloques_ens([1.0, 1.0, 1.0], [50, 0, 0]))
        self.assertEqual((nivel, seg), ("BAJA", 2))

    def test_media_intermedia(self):
        nivel, seg = nivel_confianza(_bloques_ens([2.0, 2.0, 2.0], [0, 0, 0]))
        self.assertEqual((nivel, seg), ("MEDIA", 3))

    def test_sin_ensemble_usa_heuristic(self):
        # Sin estadísticas de ensemble: la heurística de siempre
        bloques = [
            {'prob_max': 80, 'viento_dir': 'NORTE'},
            {'prob_max': 60, 'viento_dir': 'NORTE'},
            {'prob_max': 40, 'viento_dir': 'NORTE'},
        ]
        nivel, seg = nivel_confianza(bloques)
        self.assertEqual((nivel, seg), ("MEDIA", 3))


class TestRespaldoSinEnsemble(unittest.TestCase):
    """Sin ensemble, la tarjeta y el caption siguen funcionando."""

    def test_bloques_sin_ensemble(self):
        bloques = obtener_bloques_diarios(_datos_det())
        self.assertEqual(len(bloques), 3)
        self.assertEqual(bloques[0]['prob_max'], 80)  # determinista
        self.assertNotIn('prob_lluvia_ens', bloques[0])

    def test_bloques_con_ensemble_reemplazan_prob(self):
        bloques = obtener_bloques_diarios(_datos_det(),
                                          ensemble=_ensemble_ejemplo())
        self.assertEqual(bloques[0]['prob_max'], 60)      # real (ensemble)
        self.assertEqual(bloques[0]['prob_max_det'], 80)  # determinista
        self.assertEqual(bloques[0]['prob_lluvia_ens'], 60)
        self.assertAlmostEqual(bloques[0]['temp_spread'], 1.4, places=1)

    def test_tarjeta_con_y_sin_ensemble(self):
        for nombre, ens in (("sin", None), ("con", _ensemble_ejemplo())):
            ruta = f"/tmp/tarjeta_ens_{nombre}.png"
            if os.path.exists(ruta):
                os.remove(ruta)
            resultado = generar_tarjeta_diaria(_datos_det(), ruta,
                                               ensemble=ens)
            self.assertEqual(resultado, ruta)
            self.assertTrue(os.path.exists(ruta))
            self.assertGreater(os.path.getsize(ruta), 10000)
            os.remove(ruta)

    def test_caption_con_ensemble_usa_prob_real(self):
        caption = generar_caption_tarjeta(_datos_det(),
                                          ensemble=_ensemble_ejemplo())
        # Mañana: 60% real del ensemble (no 80% determinista)
        self.assertIn("60%", caption)
        self.assertLessEqual(len(caption), 1024)


class TestFetchEnsemble(unittest.TestCase):
    """Las llamadas al ensemble fallan sin tumbar nada (mock, sin red)."""

    def _respuesta(self, datos):
        mock = MagicMock()
        mock.json.return_value = datos
        mock.raise_for_status.return_value = None
        return mock

    @patch('src.clima.requests.get')
    def test_obtener_ensemble_ok(self, mock_get):
        mock_get.return_value = self._respuesta({
            'hourly': {
                'time': ['2026-11-25T00:00'],
                'temperature_2m_member01': [18.0],
                'precipitation_member01': [0.0],
            }
        })
        data = obtener_datos_ensemble(max_reintentos=1)
        self.assertIsNotNone(data)
        mock_get.assert_called_once()

    @patch('src.clima.requests.get')
    def test_obtener_ensemble_sin_miembros_none(self, mock_get):
        mock_get.return_value = self._respuesta(
            {'hourly': {'time': ['2026-11-25T00:00']}})
        self.assertIsNone(obtener_datos_ensemble(max_reintentos=1))

    @patch('src.clima.requests.get', side_effect=requests.Timeout())
    def test_obtener_ensemble_timeout_none(self, mock_get):
        self.assertIsNone(obtener_datos_ensemble(max_reintentos=1))

    @patch('src.clima.requests.get')
    def test_obtener_ensemble_navidad_ok(self, mock_get):
        mock_get.return_value = self._respuesta({
            'daily': {
                'time': ['2026-12-25'],
                'temperature_2m_min_member01': [11.0],
            }
        })
        data = obtener_datos_ensemble_navidad(max_reintentos=1)
        self.assertIsNotNone(data)
        # La gráfica de distribución necesita también la lluvia del
        # 25 dic (probabilidad de lluvia esa noche).
        params = mock_get.call_args[1]['params']
        self.assertIn('precipitation_sum', params['daily'])
        self.assertIn('temperature_2m_min', params['daily'])

    @patch('src.clima.requests.get', side_effect=requests.Timeout())
    def test_obtener_ensemble_navidad_timeout_none(self, mock_get):
        self.assertIsNone(obtener_datos_ensemble_navidad(max_reintentos=1))


class TestGraficaNavidad(unittest.TestCase):
    """Distribución de la mínima del 25 de diciembre y su imagen."""

    def test_distribucion_rangos_y_mas_probable(self):
        dist = distribucion_minima_navidad(_gfs_navidad_ejemplo())
        self.assertIsNotNone(dist)
        self.assertEqual(dist['fecha'], date(2026, 12, 25))
        self.assertEqual(dist['n_miembros'], 4)
        rangos = dict(dist['distribucion'])
        self.assertEqual(len(rangos), 10)
        self.assertEqual(rangos['15–16°'], 50)
        self.assertEqual(rangos['9–10°'], 25)
        self.assertEqual(rangos['1–5°'], 25)
        self.assertEqual(rangos['≤ 0°'], 0)
        self.assertEqual(rangos['≥ 21°'], 0)
        self.assertEqual(dist['mas_probable'], ('15–16°', 50))
        self.assertEqual(dist['prob_frio'], 50)
        self.assertEqual(dist['prob_muy_frio'], 50)
        self.assertEqual(dist['prob_lluvia'], 50)

    def test_distribucion_bordes(self):
        # Un valor en cada borde: cada uno cae en un solo rango.
        valores = [0.0, 0.5, 5.0, 6.0, 9.0, 10.0,
                   11.0, 13.0, 15.0, 17.0, 19.0, 21.0]
        datos = {'daily': {
            'time': ['2026-12-25'],
            'temperature_2m_min': [valores[0]],
        }}
        for i, v in enumerate(valores[1:], start=1):
            datos['daily'][f'temperature_2m_min_member{i:02d}'] = [v]
        dist = distribucion_minima_navidad(datos)
        rangos = dict(dist['distribucion'])
        # 12 valores: 1/12 ≈ 8%, 2/12 ≈ 17%
        self.assertEqual(rangos['≤ 0°'], 8)
        self.assertEqual(rangos['1–5°'], 17)   # 0.5 y 5.0
        self.assertEqual(rangos['6–8°'], 8)
        self.assertEqual(rangos['9–10°'], 17)  # 9.0 y 10.0
        self.assertEqual(rangos['11–12°'], 8)
        self.assertEqual(rangos['13–14°'], 8)
        self.assertEqual(rangos['15–16°'], 8)
        self.assertEqual(rangos['17–18°'], 8)
        self.assertEqual(rangos['19–20°'], 8)
        self.assertEqual(rangos['≥ 21°'], 8)
        self.assertEqual(dist['n_miembros'], 12)

    def test_distribucion_suma_cercana_a_100(self):
        # Los % son redondeados: la suma puede quedar en 99-101.
        dist = distribucion_minima_navidad(_gfs_navidad_ejemplo())
        total = sum(p for _, p in dist['distribucion'])
        self.assertIn(total, (99, 100, 101))

    def test_distribucion_sin_25_dic_none(self):
        self.assertIsNone(
            distribucion_minima_navidad(_gfs_ejemplo()))

    def test_distribucion_sin_miembros_none(self):
        self.assertIsNone(distribucion_minima_navidad(
            {'daily': {'time': ['2026-12-25']}}))
        self.assertIsNone(distribucion_minima_navidad({}))
        self.assertIsNone(distribucion_minima_navidad(None))

    def test_distribucion_sin_lluvia_no_inventa(self):
        datos = _gfs_navidad_ejemplo()
        for clave in list(datos['daily']):
            if clave.startswith('precipitation_sum'):
                del datos['daily'][clave]
        dist = distribucion_minima_navidad(datos)
        self.assertIsNotNone(dist)
        self.assertIsNone(dist['prob_lluvia'])
        self.assertEqual(dist['mas_probable'], ('15–16°', 50))

    def test_temporada(self):
        self.assertTrue(temporada_navidad(date(2026, 11, 25)))  # 30 días
        self.assertTrue(temporada_navidad(date(2026, 11, 20)))  # 35 días
        self.assertFalse(temporada_navidad(date(2026, 11, 19)))  # 36 días
        self.assertTrue(temporada_navidad(date(2026, 12, 25)))
        self.assertFalse(temporada_navidad(date(2026, 12, 26)))
        self.assertFalse(temporada_navidad(date(2026, 6, 15)))

    def test_genera_png(self):
        dist = distribucion_minima_navidad(_gfs_navidad_ejemplo())
        ruta = "/tmp/grafica_navidad_test.png"
        if os.path.exists(ruta):
            os.remove(ruta)
        resultado = generar_grafica_navidad(dist, ruta)
        self.assertEqual(resultado, ruta)
        self.assertTrue(os.path.exists(ruta))
        self.assertGreater(os.path.getsize(ruta), 10000)
        from PIL import Image
        with Image.open(ruta) as img:
            self.assertEqual(img.size, (1200, 720))
            self.assertEqual(img.format, "PNG")
        os.remove(ruta)

    def test_grafica_sin_distribucion_none(self):
        self.assertIsNone(
            generar_grafica_navidad(None, "/tmp/grafica_vacia.png"))
        self.assertIsNone(
            generar_grafica_navidad({}, "/tmp/grafica_vacia.png"))
        self.assertIsNone(
            generar_grafica_navidad({'distribucion': []},
                                    "/tmp/grafica_vacia.png"))

    def test_grafica_sin_lluvia_no_falla(self):
        datos = _gfs_navidad_ejemplo()
        for clave in list(datos['daily']):
            if clave.startswith('precipitation_sum'):
                del datos['daily'][clave]
        dist = distribucion_minima_navidad(datos)
        ruta = "/tmp/grafica_navidad_sinlluvia.png"
        if os.path.exists(ruta):
            os.remove(ruta)
        self.assertEqual(generar_grafica_navidad(dist, ruta), ruta)
        os.remove(ruta)


if __name__ == '__main__':
    unittest.main()

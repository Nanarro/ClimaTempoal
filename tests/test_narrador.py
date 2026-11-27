"""
Tests unitarios para el narrador semanal con Gemini (gratis).

El narrador es opcional y best-effort: sin llave no hay llamada de
red, y si la respuesta no pasa la validación el reporte sigue sin
la sección semanal.
"""

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

import requests

# Agregar src al path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from src.formato import generar_mensaje_completo, obtener_bloques_diarios
from src.narrador import (
    MODELO_GEMINI,
    construir_prompt,
    obtener_narrativa_semanal,
    resumen_ensemble_hoy,
    validar_narrativa,
)

FECHA = "2026-11-27"
VENTANA = ['2026-11-27', '2026-11-28', '2026-11-29', '2026-11-30',
           '2026-12-01', '2026-12-02', '2026-12-03']


def _daily_ejemplo():
    """Daily sintético de 7 días (lluvia fuerte hoy, se seca el domingo)."""
    return {
        'time': VENTANA,
        'temperature_2m_max': [17.0, 18.0, 26.0, 24.0, 23.0, 25.0, 24.0],
        'temperature_2m_min': [12.0, 14.0, 14.0, 15.0, 15.0, 16.0, 15.0],
        'precipitation_sum': [12.0, 5.0, 0.0, 0.5, 0.0, 0.0, 1.0],
        'precipitation_probability_max': [96, 60, 10, 30, 20, 10, 40],
        'weather_code': [61, 61, 1, 2, 0, 0, 3],
    }


def _datos_completos():
    """Datos completos sintéticos para generar_mensaje_completo."""
    horas, temps, sens, probs = [], [], [], []
    lluvias, vientos, rafagas, dirs = [], [], [], []
    presiones, nubes, codigos, uvs = [], [], [], []
    for h in range(24):
        horas.append(f"{FECHA}T{h:02d}:00")
        temps.append(14.0 + 0.2 * h if h < 12 else 17.0 - 0.3 * (h - 12))
        sens.append(temps[-1])
        probs.append(96 if h < 12 else (90 if h < 18 else 85))
        lluvias.append(0.5)
        vientos.append(5.0)
        rafagas.append(8.0)
        dirs.append(350.0)
        presiones.append(1018.0)
        nubes.append(90)
        codigos.append(61)
        uvs.append(0.0)
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
            **_daily_ejemplo(),
            'apparent_temperature_max': [17.0] * 7,
            'apparent_temperature_min': [12.0] * 7,
            'sunrise': [f"{d}T06:30" for d in VENTANA],
            'sunset': [f"{d}T17:45" for d in VENTANA],
            'uv_index_max': [5.0] * 7,
            'wind_speed_10m_max': [10.0] * 7,
            'wind_gusts_10m_max': [15.0] * 7,
            'wind_direction_10m_dominant': [350.0] * 7,
        },
        'current': {
            'temperature_2m': 14.0, 'apparent_temperature': 14.0,
            'relative_humidity_2m': 95, 'weather_code': 61,
            'wind_speed_10m': 5.0,
        },
    }


def _respuesta_gemini(texto):
    """Respuesta simulada de generateContent con ese texto."""
    mock = MagicMock()
    mock.json.return_value = {
        'candidates': [{'content': {'parts': [{'text': texto}]}}]
    }
    mock.raise_for_status.return_value = None
    return mock


TEXTO_BUENO = (
    "La lluvia se mantiene el sábado y se corta el domingo, cuando "
    "entra aire más seco.\n"
    "El domingo será el día más cálido de la semana, con 26 °C.\n"
    "Las mañanas siguen frescas, entre 12 y 15 °C.")


class TestConstruirPrompt(unittest.TestCase):
    """El prompt lleva los 7 días y las reglas de no inventar."""

    def test_incluye_los_7_dias_con_datos(self):
        prompt = construir_prompt(_daily_ejemplo())
        for fecha_corta in ("27/11", "28/11", "29/11", "30/11",
                            "01/12", "02/12", "03/12"):
            self.assertIn(fecha_corta, prompt)
        # Datos del primer y del tercer día
        self.assertIn("12°", prompt)
        self.assertIn("17°", prompt)
        self.assertIn("96%", prompt)
        self.assertIn("26°", prompt)
        self.assertIn("lluvia", prompt)

    def test_incluye_instrucciones_de_no_inventar(self):
        prompt = construir_prompt(_daily_ejemplo())
        self.assertIn("SOLO los datos", prompt)
        self.assertIn("no inventes", prompt)
        self.assertIn("3 o 4 líneas", prompt)

    def test_con_resumen_ensemble_incluye_bloques(self):
        resumen = {'prob_lluvia': {'POR LA MAÑANA': 100, 'TARDE': 90,
                                   'NOCHE': 80},
                   'confianza': 'ALTA'}
        prompt = construir_prompt(_daily_ejemplo(), resumen)
        self.assertIn("100%", prompt)
        self.assertIn("ALTA", prompt)
        self.assertIn("ensemble", prompt.lower())


class TestResumenEnsembleHoy(unittest.TestCase):
    """El resumen de hoy sale de los bloques del ensemble."""

    def test_prob_por_bloque_y_confianza(self):
        bloques = [
            {'nombre': 'POR LA MAÑANA', 'temp_spread': 0.5,
             'prob_lluvia_ens': 100},
            {'nombre': 'TARDE', 'temp_spread': 0.6,
             'prob_lluvia_ens': 90},
            {'nombre': 'NOCHE', 'temp_spread': 0.5,
             'prob_lluvia_ens': 80},
        ]
        resumen = resumen_ensemble_hoy(bloques)
        self.assertEqual(resumen['prob_lluvia']['POR LA MAÑANA'], 100)
        self.assertEqual(resumen['prob_lluvia']['NOCHE'], 80)
        self.assertEqual(resumen['confianza'], 'ALTA')

    def test_sin_bloques_dict_vacio(self):
        self.assertEqual(resumen_ensemble_hoy([]), {})
        self.assertEqual(resumen_ensemble_hoy(None), {})

    def test_sin_ensemble_usa_prob_determinista(self):
        bloques = [
            {'nombre': 'POR LA MAÑANA', 'prob_max': 38},
            {'nombre': 'TARDE', 'prob_max': 92},
            {'nombre': 'NOCHE', 'prob_max': 96},
        ]
        resumen = resumen_ensemble_hoy(bloques)
        self.assertEqual(resumen['prob_lluvia']['TARDE'], 92)


class TestValidarNarrativa(unittest.TestCase):
    """La validación deja pasar lo bueno y frena lo inventado."""

    def test_texto_bueno_aceptado(self):
        self.assertTrue(validar_narrativa(TEXTO_BUENO, VENTANA))

    def test_fecha_dentro_de_la_ventana_aceptada(self):
        texto = ("El sábado 28 de noviembre se mantiene la lluvia.\n"
                 "El domingo amanece más seco.")
        self.assertTrue(validar_narrativa(texto, VENTANA))

    def test_rechaza_ano(self):
        self.assertFalse(validar_narrativa(
            "Como en 2026, lloverá toda la semana.\nSegunda línea.",
            VENTANA))

    def test_rechaza_record(self):
        self.assertFalse(validar_narrativa(
            "Será un récord de lluvia para Tempoal.\nSegunda línea.",
            VENTANA))
        self.assertFalse(validar_narrativa(
            "Un record de frío esta semana.\nSegunda línea.",
            VENTANA))

    def test_rechaza_historico(self):
        self.assertFalse(validar_narrativa(
            "El frío más histórico de los últimos años.\nSegunda línea.",
            VENTANA))
        self.assertFalse(validar_narrativa(
            "Una semana historica para la región.\nSegunda línea.",
            VENTANA))

    def test_rechaza_fecha_fuera_de_la_ventana(self):
        # La ventana es 27 nov – 3 dic: el 7 de diciembre no está
        self.assertFalse(validar_narrativa(
            "El 7 de diciembre llegará otro frente frío.\nSegunda línea.",
            VENTANA))

    def test_rechaza_texto_vacio(self):
        self.assertFalse(validar_narrativa("", VENTANA))
        self.assertFalse(validar_narrativa("   \n  ", VENTANA))
        self.assertFalse(validar_narrativa(None, VENTANA))

    def test_rechaza_mas_de_700_caracteres(self):
        texto = ("Línea larga. " * 60).strip() + "\nSegunda línea."
        self.assertGreater(len(texto), 700)
        self.assertFalse(validar_narrativa(texto, VENTANA))

    def test_rechaza_mas_de_5_lineas(self):
        texto = "\n".join(f"Línea {i}." for i in range(1, 7))
        self.assertFalse(validar_narrativa(texto, VENTANA))


class TestObtenerNarrativa(unittest.TestCase):
    """La llamada a Gemini es best-effort y nunca lanza excepciones."""

    def test_exito_devuelve_texto_validado(self):
        with patch('src.narrador.requests.post') as mock_post:
            mock_post.return_value = _respuesta_gemini(TEXTO_BUENO)
            texto = obtener_narrativa_semanal(_daily_ejemplo(),
                                              api_key="llave-falsa")
        self.assertEqual(texto, TEXTO_BUENO)
        mock_post.assert_called_once()
        url_llamada = mock_post.call_args[0][0]
        self.assertIn(MODELO_GEMINI, url_llamada)
        self.assertIn("generateContent", url_llamada)
        # La llave va en header, nunca en la URL ni en el cuerpo
        self.assertNotIn("llave-falsa", url_llamada)
        self.assertNotIn("llave-falsa",
                         str(mock_post.call_args[1].get('json', '')))

    def test_error_de_red_devuelve_none(self):
        with patch('src.narrador.requests.post',
                   side_effect=requests.Timeout()):
            self.assertIsNone(obtener_narrativa_semanal(
                _daily_ejemplo(), api_key="llave-falsa"))

    def test_respuesta_sin_candidatos_devuelve_none(self):
        mock = MagicMock()
        mock.json.return_value = {'candidates': []}
        mock.raise_for_status.return_value = None
        with patch('src.narrador.requests.post', return_value=mock):
            self.assertIsNone(obtener_narrativa_semanal(
                _daily_ejemplo(), api_key="llave-falsa"))

    def test_texto_invalido_devuelve_none(self):
        with patch('src.narrador.requests.post') as mock_post:
            mock_post.return_value = _respuesta_gemini(
                "Como en 2026, será un récord histórico.\nSegunda línea.")
            self.assertIsNone(obtener_narrativa_semanal(
                _daily_ejemplo(), api_key="llave-falsa"))

    def test_sin_llave_no_hay_llamada_de_red(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop('GEMINI_API_KEY', None)
            with patch('src.narrador.requests.post') as mock_post:
                self.assertIsNone(obtener_narrativa_semanal(
                    _daily_ejemplo(), api_key=None))
                mock_post.assert_not_called()

    def test_llave_por_variable_de_entorno(self):
        with patch.dict(os.environ, {'GEMINI_API_KEY': 'llave-env'}):
            with patch('src.narrador.requests.post') as mock_post:
                mock_post.return_value = _respuesta_gemini(TEXTO_BUENO)
                self.assertEqual(
                    obtener_narrativa_semanal(_daily_ejemplo()),
                    TEXTO_BUENO)
                headers = mock_post.call_args[1]['headers']
                self.assertEqual(headers['x-goog-api-key'], 'llave-env')

    def test_error_http_devuelve_none(self):
        mock = MagicMock()
        mock.raise_for_status.side_effect = requests.HTTPError(
            response=MagicMock(status_code=400))
        with patch('src.narrador.requests.post', return_value=mock):
            self.assertIsNone(obtener_narrativa_semanal(
                _daily_ejemplo(), api_key="llave-falsa"))

    def test_con_ensemble_crudo_incluye_resumen_en_prompt(self):
        # Ensemble sintético de 5 miembros: llueve en los 3 bloques
        horas = [f"{FECHA}T{h:02d}:00" for h in range(24)]
        hourly = {'time': horas}
        for m in range(1, 6):
            hourly[f'temperature_2m_member{m:02d}'] = [15.0] * 24
            hourly[f'precipitation_member{m:02d}'] = [0.5] * 24
        ensemble = {'hourly': hourly}
        with patch('src.narrador.requests.post') as mock_post:
            mock_post.return_value = _respuesta_gemini(TEXTO_BUENO)
            texto = obtener_narrativa_semanal(
                _daily_ejemplo(), ensemble=ensemble, api_key="k")
        self.assertEqual(texto, TEXTO_BUENO)
        prompt = mock_post.call_args[1]['json']['contents'][0]['parts'][0]['text']
        self.assertIn("100%", prompt)  # 5/5 miembros con lluvia
        self.assertIn("ensemble", prompt.lower())


class TestIntegracionMensaje(unittest.TestCase):
    """La sección semanal aparece solo cuando hay narrativa."""

    def test_mensaje_con_narrativa_incluye_seccion(self):
        mensaje = generar_mensaje_completo(
            _datos_completos(), [], [],
            semana_narrativa="Línea de prueba.")
        self.assertIsNotNone(mensaje)
        self.assertIn("LA SEMANA EN TEMPOAL", mensaje)
        self.assertIn("Línea de prueba.", mensaje)
        # La sección va después de PRÓXIMOS 3 DÍAS
        self.assertLess(mensaje.index("PRÓXIMOS 3 DÍAS"),
                        mensaje.index("LA SEMANA EN TEMPOAL"))

    def test_mensaje_sin_narrativa_no_incluye_seccion(self):
        mensaje = generar_mensaje_completo(_datos_completos(), [], [])
        self.assertIsNotNone(mensaje)
        self.assertNotIn("LA SEMANA EN TEMPOAL", mensaje)
        mensaje_vacio = generar_mensaje_completo(
            _datos_completos(), [], [], semana_narrativa="   ")
        self.assertNotIn("LA SEMANA EN TEMPOAL", mensaje_vacio)


if __name__ == '__main__':
    unittest.main()

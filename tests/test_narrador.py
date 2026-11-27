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

from src.formato import (
    generar_caption_navidad,
    generar_mensaje_completo,
    obtener_bloques_diarios,
)
from src.narrador import (
    MODELO_GEMINI,
    construir_prompt,
    construir_prompt_alertas,
    construir_prompt_dia,
    construir_prompt_navidad,
    llamar_gemini,
    obtener_explicacion_alertas,
    obtener_interpretacion_navidad,
    obtener_narrativa_dia,
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


def _probs_navidad_ejemplo():
    """Probabilidades de frío por día, como calcular_probabilidades_frio.

    28 días (28 nov – 25 dic): el frío sube hacia el 19-21 dic (pico
    37%) y el 25 de diciembre marca 40% (<12 °C) y 23% (<10 °C).
    """
    from datetime import date, timedelta
    inicio = date(2026, 11, 28)
    probs = []
    for i in range(28):
        fecha = inicio + timedelta(days=i)
        if fecha.day == 25 and fecha.month == 12:
            frio, muy_frio = 40, 23
        elif fecha.day in (19, 20, 21) and fecha.month == 12:
            frio, muy_frio = 37, 20
        elif fecha.month == 12:
            frio, muy_frio = 25, 12
        else:
            frio, muy_frio = 10, 3
        probs.append({'fecha': fecha, 'sin_datos': False,
                      'prob_frio': frio, 'prob_muy_frio': muy_frio,
                      'n_miembros': 30})
    return probs


def _alertas_ejemplo():
    """Una alerta tal como la construye analizar_riesgos_climaticos."""
    return ["🌧️ <b>VIERNES 27/11: LLUVIA INTENSA</b>\n"
            "   💧 Acumulado: 22 mm\n"
            "   ☂️ No olvides paraguas"]


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
        # La llave viaja como ?key= en la URL (patrón REST de Google)
        self.assertIn("key=llave-falsa", url_llamada)
        # ...y nunca en el header ni en el cuerpo
        self.assertNotIn("llave-falsa",
                         str(mock_post.call_args[1].get('headers', '')))
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
                url_llamada = mock_post.call_args[0][0]
                self.assertIn("key=llave-env", url_llamada)
                headers = mock_post.call_args[1]['headers']
                self.assertNotIn('x-goog-api-key', headers)

    def test_error_http_devuelve_none(self):
        mock = MagicMock()
        mock.raise_for_status.side_effect = requests.HTTPError(
            response=MagicMock(status_code=400))
        with patch('src.narrador.requests.post', return_value=mock):
            self.assertIsNone(obtener_narrativa_semanal(
                _daily_ejemplo(), api_key="llave-falsa"))

    def test_error_http_registra_el_mensaje_del_cuerpo(self):
        # Un 404 con el mensaje de Google queda en el log, para que el
        # próximo fallo se diagnostique solo (p. ej. modelo no válido).
        mock = MagicMock()
        mock.json.return_value = {
            'error': {'message': 'models/gemini-2.5-flash is not found'}}
        mock.raise_for_status.side_effect = requests.HTTPError(
            response=mock)
        mock.status_code = 404
        with patch('src.narrador.requests.post', return_value=mock):
            with self.assertLogs('src.utils', level='WARNING') as logs:
                self.assertIsNone(obtener_narrativa_semanal(
                    _daily_ejemplo(), api_key="llave-falsa"))
        self.assertTrue(any('is not found' in linea
                            for linea in logs.output))

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


class TestLlamarGemini(unittest.TestCase):
    """El helper compartido: una llamada, nunca excepciones."""

    def test_exito_devuelve_texto(self):
        with patch('src.narrador.requests.post') as mock_post:
            mock_post.return_value = _respuesta_gemini("Hola.")
            self.assertEqual(
                llamar_gemini("prompt", "llave-falsa"), "Hola.")
            mock_post.assert_called_once()

    def test_sin_llave_no_hay_llamada_de_red(self):
        with patch('src.narrador.requests.post') as mock_post:
            self.assertIsNone(llamar_gemini("prompt", None))
            self.assertIsNone(llamar_gemini("prompt", "   "))
            mock_post.assert_not_called()

    def test_error_http_devuelve_none(self):
        mock = MagicMock()
        mock.raise_for_status.side_effect = requests.HTTPError(
            response=MagicMock(status_code=429))
        with patch('src.narrador.requests.post', return_value=mock):
            self.assertIsNone(llamar_gemini("prompt", "k"))


class TestConstruirPromptDia(unittest.TestCase):
    """El prompt del día lleva hoy: ahora, bloques, 24 h y presión."""

    def test_incluye_condiciones_actuales_y_bloques(self):
        prompt = construir_prompt_dia(_datos_completos())
        self.assertIn("14.0 °C", prompt)
        self.assertIn("95%", prompt)
        self.assertIn("POR LA MAÑANA", prompt)
        self.assertIn("TARDE", prompt)
        self.assertIn("NOCHE", prompt)
        self.assertIn("96%", prompt)  # prob. del bloque de la mañana
        self.assertIn("Amanecer 06:30", prompt)
        self.assertIn("Atardecer 17:45", prompt)
        self.assertIn("Confianza", prompt)

    def test_incluye_resumen_24h_y_presion(self):
        prompt = construir_prompt_dia(_datos_completos())
        self.assertIn("mínima 13.7 °C", prompt)
        self.assertIn("máxima 17.0 °C", prompt)
        self.assertIn("Presión:", prompt)

    def test_con_ensemble_marca_probabilidad_real(self):
        horas = [f"{FECHA}T{h:02d}:00" for h in range(24)]
        hourly = {'time': horas}
        for m in range(1, 6):
            hourly[f'temperature_2m_member{m:02d}'] = [15.0] * 24
            hourly[f'precipitation_member{m:02d}'] = [0.5] * 24
        prompt = construir_prompt_dia(_datos_completos(),
                                      ensemble={'hourly': hourly})
        self.assertIn("100%", prompt)
        self.assertIn("ensemble ECMWF", prompt)

    def test_instrucciones_de_no_inventar(self):
        prompt = construir_prompt_dia(_datos_completos())
        self.assertIn("SOLO los datos", prompt)
        self.assertIn("no inventes", prompt)
        self.assertIn("3 a 5 líneas", prompt)
        self.assertIn("no escribas años", prompt)


class TestConstruirPromptNavidad(unittest.TestCase):
    """El prompt de Navidad lleva la distribución de 30 días."""

    def test_incluye_dias_probabilidades_y_25(self):
        prompt = construir_prompt_navidad(_probs_navidad_ejemplo())
        self.assertIn("28/11", prompt)
        self.assertIn("25/12", prompt)
        self.assertIn("40%", prompt)  # el 25 de diciembre
        self.assertIn("37%", prompt)  # el pico 19-21 dic
        self.assertIn("Tendencia:", prompt)

    def test_instrucciones_de_no_inventar(self):
        prompt = construir_prompt_navidad(_probs_navidad_ejemplo())
        self.assertIn("SOLO", prompt)
        self.assertIn("no inventes", prompt)
        self.assertIn("1 o 2 líneas", prompt)


class TestConstruirPromptAlertas(unittest.TestCase):
    """El prompt de alertas lleva las alertas limpias de HTML."""

    def test_incluye_alertas_sin_html(self):
        prompt = construir_prompt_alertas(_alertas_ejemplo())
        self.assertIn("LLUVIA INTENSA", prompt)
        self.assertIn("22 mm", prompt)
        self.assertIn("VIERNES 27/11", prompt)
        self.assertNotIn("<b>", prompt)
        self.assertNotIn("</b>", prompt)

    def test_instrucciones_de_no_inventar(self):
        prompt = construir_prompt_alertas(_alertas_ejemplo())
        self.assertIn("SOLO la información", prompt)
        self.assertIn("no inventes", prompt)


TEXTO_DIA_BUENO = (
    "La lluvia se mantiene todo el día, más fuerte por la mañana "
    "con 96% de probabilidad.\n"
    "Hará frío, con máxima de 17 °C y mínima de 14 °C.\n"
    "La presión se mantiene estable, así que la lluvia seguirá.")


class TestObtenerNarrativaDia(unittest.TestCase):
    """La narrativa del día es best-effort y nunca lanza excepciones."""

    def test_exito_devuelve_texto_validado(self):
        with patch('src.narrador.requests.post') as mock_post:
            mock_post.return_value = _respuesta_gemini(TEXTO_DIA_BUENO)
            texto = obtener_narrativa_dia(_datos_completos(),
                                          api_key="llave-falsa")
        self.assertEqual(texto, TEXTO_DIA_BUENO)

    def test_error_de_red_devuelve_none(self):
        with patch('src.narrador.requests.post',
                   side_effect=requests.Timeout()):
            self.assertIsNone(obtener_narrativa_dia(
                _datos_completos(), api_key="llave-falsa"))

    def test_texto_invalido_devuelve_none(self):
        with patch('src.narrador.requests.post') as mock_post:
            mock_post.return_value = _respuesta_gemini(
                "Como en 2026, lloverá todo el día.\nSegunda línea.")
            self.assertIsNone(obtener_narrativa_dia(
                _datos_completos(), api_key="llave-falsa"))

    def test_fecha_de_manana_rechazada(self):
        # La ventana del día es solo hoy: mencionar el 28 de
        # noviembre (mañana) no pasa la validación
        with patch('src.narrador.requests.post') as mock_post:
            mock_post.return_value = _respuesta_gemini(
                "Hoy llueve y el 28 de noviembre seguirá lloviendo.\n"
                "Segunda línea.")
            self.assertIsNone(obtener_narrativa_dia(
                _datos_completos(), api_key="llave-falsa"))

    def test_sin_llave_no_hay_llamada_de_red(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop('GEMINI_API_KEY', None)
            with patch('src.narrador.requests.post') as mock_post:
                self.assertIsNone(obtener_narrativa_dia(
                    _datos_completos(), api_key=None))
                mock_post.assert_not_called()


TEXTO_NAVIDAD_BUENO = (
    "El frío se concentra entre el 19 y el 21 de diciembre, con 37% "
    "de probabilidad.\n"
    "El 25 de diciembre pinta frío, con 40% de probabilidad de "
    "mínima menor a 12 °C.")


class TestObtenerInterpretacionNavidad(unittest.TestCase):
    """La lectura de la gráfica es best-effort y nunca lanza."""

    def test_exito_devuelve_texto_validado(self):
        with patch('src.narrador.requests.post') as mock_post:
            mock_post.return_value = _respuesta_gemini(TEXTO_NAVIDAD_BUENO)
            texto = obtener_interpretacion_navidad(
                _probs_navidad_ejemplo(), api_key="llave-falsa")
        self.assertEqual(texto, TEXTO_NAVIDAD_BUENO)

    def test_sin_datos_devuelve_none(self):
        self.assertIsNone(obtener_interpretacion_navidad(
            [], api_key="llave-falsa"))
        sin_datos = [{'fecha': p['fecha'], 'sin_datos': True,
                      'prob_frio': None, 'prob_muy_frio': None,
                      'n_miembros': 0}
                     for p in _probs_navidad_ejemplo()]
        self.assertIsNone(obtener_interpretacion_navidad(
            sin_datos, api_key="llave-falsa"))

    def test_error_http_devuelve_none(self):
        mock = MagicMock()
        mock.raise_for_status.side_effect = requests.HTTPError(
            response=MagicMock(status_code=400))
        with patch('src.narrador.requests.post', return_value=mock):
            self.assertIsNone(obtener_interpretacion_navidad(
                _probs_navidad_ejemplo(), api_key="llave-falsa"))

    def test_texto_invalido_devuelve_none(self):
        with patch('src.narrador.requests.post') as mock_post:
            mock_post.return_value = _respuesta_gemini(
                "Será un récord de frío en 2026.\nSegunda línea.")
            self.assertIsNone(obtener_interpretacion_navidad(
                _probs_navidad_ejemplo(), api_key="llave-falsa"))

    def test_sin_llave_no_hay_llamada_de_red(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop('GEMINI_API_KEY', None)
            with patch('src.narrador.requests.post') as mock_post:
                self.assertIsNone(obtener_interpretacion_navidad(
                    _probs_navidad_ejemplo(), api_key=None))
                mock_post.assert_not_called()


TEXTO_ALERTAS_BUENO = (
    "Lluvia intensa de 22 mm: lloverá mucho en poco tiempo, puede "
    "haber encharcamientos.\n"
    "Evita cruzar arroyos y maneja con cuidado.")


class TestObtenerExplicacionAlertas(unittest.TestCase):
    """La explicación de alertas es best-effort y nunca lanza."""

    def test_exito_devuelve_texto_validado(self):
        with patch('src.narrador.requests.post') as mock_post:
            mock_post.return_value = _respuesta_gemini(TEXTO_ALERTAS_BUENO)
            texto = obtener_explicacion_alertas(
                _alertas_ejemplo(), api_key="llave-falsa",
                fechas_ventana=VENTANA)
        self.assertEqual(texto, TEXTO_ALERTAS_BUENO)

    def test_sin_alertas_devuelve_none_sin_red(self):
        with patch('src.narrador.requests.post') as mock_post:
            self.assertIsNone(obtener_explicacion_alertas(
                [], api_key="llave-falsa"))
            self.assertIsNone(obtener_explicacion_alertas(
                None, api_key="llave-falsa"))
            mock_post.assert_not_called()

    def test_error_de_red_devuelve_none(self):
        with patch('src.narrador.requests.post',
                   side_effect=requests.ConnectionError()):
            self.assertIsNone(obtener_explicacion_alertas(
                _alertas_ejemplo(), api_key="llave-falsa",
                fechas_ventana=VENTANA))

    def test_sin_llave_no_hay_llamada_de_red(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop('GEMINI_API_KEY', None)
            with patch('src.narrador.requests.post') as mock_post:
                self.assertIsNone(obtener_explicacion_alertas(
                    _alertas_ejemplo(), api_key=None,
                    fechas_ventana=VENTANA))
                mock_post.assert_not_called()


class TestGenerarCaptionNavidad(unittest.TestCase):
    """El caption de Navidad: base igual y lectura opcional."""

    BASE = ("🎄 <b>¿FRÍO EN NAVIDAD?</b> Probabilidad de mínima menor a "
            "12 °C rumbo al 25 de diciembre, según el ensemble GFS "
            "(31 miembros). A 30 días la incertidumbre es muy alta.")

    def test_sin_interpretacion_es_el_caption_base(self):
        self.assertEqual(
            generar_caption_navidad(_probs_navidad_ejemplo()), self.BASE)
        self.assertEqual(generar_caption_navidad([], None), self.BASE)
        self.assertEqual(
            generar_caption_navidad(_probs_navidad_ejemplo(), ""), self.BASE)

    def test_con_interpretacion_se_agrega_al_final(self):
        caption = generar_caption_navidad(
            _probs_navidad_ejemplo(), interpretacion=TEXTO_NAVIDAD_BUENO)
        self.assertTrue(caption.startswith(self.BASE))
        self.assertIn(TEXTO_NAVIDAD_BUENO, caption)
        self.assertLessEqual(len(caption), 1000)

    def test_interpretacion_larga_se_recorta_sin_tocar_la_base(self):
        larga = "Palabra " * 200
        caption = generar_caption_navidad(
            _probs_navidad_ejemplo(), interpretacion=larga)
        self.assertTrue(caption.startswith(self.BASE))
        self.assertLessEqual(len(caption), 1000)


class TestIntegracionMensajeGemini(unittest.TestCase):
    """Las 3 narrativas nuevas aparecen solo donde les toca."""

    def test_narrativa_dia_va_despues_de_la_fecha(self):
        mensaje = generar_mensaje_completo(
            _datos_completos(), [], [],
            narrativa_dia="Párrafo de prueba del día.")
        self.assertIsNotNone(mensaje)
        self.assertIn("Párrafo de prueba del día.", mensaje)
        self.assertLess(mensaje.index("MONITOREO PROTECCIÓN CIVIL"),
                        mensaje.index("Párrafo de prueba del día."))
        self.assertLess(mensaje.index("Párrafo de prueba del día."),
                        mensaje.index("RESUMEN EJECUTIVO"))

    def test_sin_narrativa_dia_no_aparece_nada_extra(self):
        mensaje = generar_mensaje_completo(_datos_completos(), [], [])
        self.assertIsNotNone(mensaje)
        self.assertNotIn("Párrafo de prueba", mensaje)

    def test_explicacion_alertas_dentro_de_la_seccion(self):
        mensaje = generar_mensaje_completo(
            _datos_completos(), _alertas_ejemplo(), [],
            explicacion_alertas="Explicación de prueba.")
        self.assertIsNotNone(mensaje)
        self.assertIn("Explicación de prueba.", mensaje)
        self.assertLess(mensaje.index("ALERTAS METEOROLÓGICAS"),
                        mensaje.index("Explicación de prueba."))
        self.assertLess(mensaje.index("Explicación de prueba."),
                        mensaje.index("ESTADÍSTICAS SEMANALES"))

    def test_explicacion_sin_alertas_no_aparece(self):
        mensaje = generar_mensaje_completo(
            _datos_completos(), [], [],
            explicacion_alertas="Explicación de prueba.")
        self.assertIsNotNone(mensaje)
        self.assertNotIn("Explicación de prueba.", mensaje)
        self.assertIn("Sin alertas meteorológicas", mensaje)


if __name__ == '__main__':
    unittest.main()

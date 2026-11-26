"""
Tests unitarios para el interpretador de datos (src/interpretador.py).

Reglas que se verifican (aprobadas por el usuario 2026-11-26):
- El viento flojo no aparece; el viento fuerte se interpreta (qué causa).
- La presión normal no aparece; en caída/subida se interpreta.
- La temperatura se dice como sensación; mín/máx solo si el rango importa.
- La lluvia se dice con palabras decisivas según la probabilidad real.
- La comparación especial solo sale en casos excepcionales y nunca
  inventa eventos, fechas ni récords: solo superlativos verificados
  contra la ventana de 7 días o referencias genéricas sin fecha.
"""

import os
import re
import sys
import unittest

# Agregar src al path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from src.formato import (
    extraer_ensemble_bloque,
    generar_conclusiones_bloques,
    generar_mensaje_completo,
    obtener_bloques_diarios,
)
from src.interpretador import (
    advertencia_confianza,
    comparacion_especial,
    frase_lluvia,
    frase_presion_dia,
    frase_temperatura,
    frase_viento,
    interpretar_bloque,
    interpretar_dia,
    recomendacion_practica,
    resumen_dia,
)

FECHA = "2026-11-26"


def _bloque(**cambios):
    """Bloque sintético con valores por defecto (día tranquilo)."""
    bloque = {
        'nombre': 'MAÑANA',
        'horas': '06–12 h',
        'codigo': 3,
        'prob_max': 0,
        'prob_lluvia_fuerte_ens': None,
        'lluvia_mm': 0.0,
        'temp_media': 20.0,
        'sensacion_media': 20.0,
        'temp_min': 19.0,
        'temp_max': 21.0,
        'viento_dir': 'NORTE',
        'viento_min': 3.0,
        'viento_max': 5.0,
        'rafaga_max': 8.0,
        'presion_media': 1018,
        'nubosidad_media': 50,
    }
    bloque.update(cambios)
    return bloque


def _bloques_hoy():
    """Los 3 bloques de hoy, día lluvioso como el 26 de noviembre."""
    return [
        _bloque(nombre='MAÑANA', prob_max=38, lluvia_mm=1.0,
                temp_media=15.0, sensacion_media=15.0,
                temp_min=12.0, temp_max=17.0,
                viento_dir='OESTE', viento_min=4.0, viento_max=6.0,
                rafaga_max=9.0, presion_media=1018, nubosidad_media=90),
        _bloque(nombre='TARDE', prob_max=92, lluvia_mm=8.0,
                prob_lluvia_fuerte_ens=20,
                temp_media=16.0, sensacion_media=16.0,
                temp_min=16.0, temp_max=16.0,
                viento_dir='NORESTE', viento_min=5.0, viento_max=7.0,
                rafaga_max=11.0, presion_media=1017, nubosidad_media=95),
        _bloque(nombre='NOCHE', prob_max=96, lluvia_mm=9.0,
                prob_lluvia_fuerte_ens=30,
                temp_media=15.0, sensacion_media=15.0,
                temp_min=14.0, temp_max=16.0,
                viento_dir='NORTE', viento_min=2.0, viento_max=4.0,
                rafaga_max=7.0, presion_media=1019, nubosidad_media=95),
    ]


def _daily_7d(**cambios):
    """Ventana diaria de 7 días (hoy = índice 0)."""
    daily = {
        'time': [FECHA, '2026-11-27', '2026-11-28', '2026-11-29',
                 '2026-11-30', '2026-12-01', '2026-12-02'],
        'temperature_2m_max': [17.0, 22.0, 23.0, 24.0, 25.0, 24.0, 23.0],
        'temperature_2m_min': [12.0, 15.0, 16.0, 17.0, 17.0, 16.0, 15.0],
        'precipitation_probability_max': [96, 60, 40, 30, 20, 10, 10],
        'precipitation_sum': [12.0, 5.0, 2.0, 1.0, 0.0, 0.0, 0.0],
        'wind_speed_10m_max': [10.0, 25.0, 20.0, 18.0, 15.0, 12.0, 12.0],
        'wind_gusts_10m_max': [15.0, 38.0, 30.0, 27.0, 22.0, 18.0, 18.0],
    }
    daily.update(cambios)
    return daily


class TestFraseLluvia(unittest.TestCase):
    """Palabras decisivas según la probabilidad (y la de lluvia fuerte)."""

    def test_casi_segura_con_fuerte(self):
        f = frase_lluvia(_bloque(prob_max=95, prob_lluvia_fuerte_ens=60))
        self.assertIn("casi segura", f)
        self.assertIn("95%", f)
        self.assertIn("fuerte", f)

    def test_casi_segura_pero_ligera(self):
        # 92% dice que llueve, pero casi ningún miembro ve lluvia fuerte:
        # el ensemble distingue "seguro pero ligero" de "seguro y fuerte".
        f = frase_lluvia(_bloque(prob_max=92, prob_lluvia_fuerte_ens=10))
        self.assertIn("casi segura", f)
        self.assertIn("ligera", f)

    def test_muy_probable_y_probable(self):
        self.assertIn("muy probable",
                      frase_lluvia(_bloque(prob_max=75)))
        self.assertIn("probable que llueva",
                      frase_lluvia(_bloque(prob_max=60)))

    def test_llovizna_ocasional(self):
        f = frase_lluvia(_bloque(prob_max=38))
        self.assertIn("llovizna", f)
        self.assertIn("38%", f)

    def test_sin_lluvia(self):
        self.assertEqual(frase_lluvia(_bloque(prob_max=5)),
                         "sin lluvia esperada")

    def test_sin_ensemble_usa_acumulado(self):
        # Sin prob de lluvia fuerte, el acumulado determinista decide.
        f = frase_lluvia(_bloque(prob_max=92, lluvia_mm=12.0))
        self.assertIn("fuerte", f)


class TestFraseViento(unittest.TestCase):
    """El viento flojo no aparece; el fuerte dice qué causa."""

    def test_viento_flojo_se_omite(self):
        self.assertIsNone(frase_viento(_bloque(viento_max=5.0)))
        self.assertIsNone(frase_viento(_bloque(viento_max=9.0)))

    def test_viento_fuerte_con_riesgo(self):
        f = frase_viento(_bloque(viento_max=45.0, rafaga_max=55.0,
                                 viento_dir='NORTE', temp_media=15.0))
        self.assertIn("fuerte", f)
        self.assertIn("ramas", f)
        self.assertIn("55 km/h", f)  # la ráfaga sí es dato que importa

    def test_viento_moderado_lluvia(self):
        f = frase_viento(_bloque(viento_max=25.0, prob_max=80,
                                 viento_dir='NORTE'))
        self.assertIn("empujará la lluvia", f)

    def test_viento_ligero_frio_norte(self):
        f = frase_viento(_bloque(viento_max=15.0, viento_dir='NORTE',
                                 temp_media=15.0))
        self.assertIn("más frío", f)

    def test_viento_ligero_sin_efecto_se_omite(self):
        # 15 km/h del este, templado y seco: no causa nada.
        self.assertIsNone(frase_viento(_bloque(
            viento_max=15.0, viento_dir='ESTE', temp_media=22.0,
            prob_max=5)))


class TestFraseTemperatura(unittest.TestCase):
    """Sensación primero; mín/máx solo si el rango importa."""

    def test_frio_con_sensacion(self):
        f = frase_temperatura(_bloque(temp_media=15.0,
                                      sensacion_media=15.0))
        self.assertIn("frío", f)
        self.assertIn("15 °C", f)

    def test_sensacion_muy_distinta(self):
        f = frase_temperatura(_bloque(temp_media=15.0,
                                      sensacion_media=11.0))
        self.assertIn("se sentirá de 11", f)

    def test_sensacion_parecida_no_se_menciona(self):
        f = frase_temperatura(_bloque(temp_media=15.0,
                                      sensacion_media=14.0))
        self.assertNotIn("sentirá", f)

    def test_rango_amplio_muestra_min_max(self):
        f = frase_temperatura(_bloque(temp_media=15.0, temp_min=12.0,
                                      temp_max=17.0))
        self.assertIn("mín. 12°", f)
        self.assertIn("máx. 17°", f)

    def test_rango_corto_no_muestra_min_max(self):
        f = frase_temperatura(_bloque(temp_media=20.0, temp_min=19.0,
                                      temp_max=21.0))
        self.assertNotIn("mín.", f)


class TestFrasePresionDia(unittest.TestCase):
    """La presión normal no aparece; en caída/subida se interpreta."""

    def test_presion_normal_se_omite(self):
        self.assertIsNone(frase_presion_dia(_bloques_hoy()))

    def test_presion_en_caida(self):
        bloques = [
            _bloque(presion_media=1020),
            _bloque(presion_media=1017),
            _bloque(presion_media=1014),
        ]
        f = frase_presion_dia(bloques)
        self.assertIn("bajando", f)

    def test_presion_en_subida(self):
        bloques = [
            _bloque(presion_media=1012),
            _bloque(presion_media=1015),
            _bloque(presion_media=1018),
        ]
        self.assertIn("subiendo", frase_presion_dia(bloques))

    def test_presion_baja_absoluta(self):
        bloques = [
            _bloque(presion_media=1002),
            _bloque(presion_media=1001),
            _bloque(presion_media=1000),
        ]
        self.assertIn("baja", frase_presion_dia(bloques))

    def test_sin_datos_none(self):
        bloques = [_bloque(presion_media=None) for _ in range(3)]
        self.assertIsNone(frase_presion_dia(bloques))


class TestResumenYRecomendacion(unittest.TestCase):
    """Resumen decisivo del día y cierre práctico."""

    def test_dia_lluvioso_y_frio(self):
        r = resumen_dia(_bloques_hoy())
        self.assertIn("día de lluvias", r)
        self.assertIn("frío", r)

    def test_dia_seco(self):
        bloques = [_bloque(nubosidad_media=20) for _ in range(3)]
        self.assertIn("despejado", resumen_dia(bloques))

    def test_advertencia_solo_con_baja(self):
        self.assertIsNotNone(advertencia_confianza("BAJA"))
        self.assertIsNone(advertencia_confianza("MEDIA"))
        self.assertIsNone(advertencia_confianza("ALTA"))

    def test_recomendacion_paraguas_tarde_noche(self):
        r = recomendacion_practica(_bloques_hoy())
        self.assertIn("paraguas", r)
        self.assertIn("tarde y la noche", r)

    def test_sin_recomendacion_si_nada_aplica(self):
        bloques = [_bloque() for _ in range(3)]
        self.assertIsNone(recomendacion_practica(bloques))

    def test_recomendacion_viento_fuerte(self):
        bloques = [_bloque(viento_max=45.0, rafaga_max=55.0)]
        self.assertIn("ramas", recomendacion_practica(bloques))


class TestComparacionEspecial(unittest.TestCase):
    """Solo en casos excepcionales y sin inventar nada."""

    def test_dia_normal_sin_comparacion(self):
        # Día normal: templado (máx. 24 °C), lluvia moderada, sin
        # viento fuerte. Ningún disparador excepcional se activa.
        bloques = [_bloque(temp_media=22.0, sensacion_media=22.0,
                           temp_min=20.0, temp_max=24.0, prob_max=30,
                           viento_max=6.0)
                   for _ in range(3)]
        self.assertIsNone(comparacion_especial(bloques, _daily_7d()))

    def test_dia_mas_lluvioso_de_la_semana(self):
        bloques = [_bloque(prob_max=95, lluvia_mm=12.0)
                   for _ in range(3)]
        f = comparacion_especial(bloques, _daily_7d())
        self.assertEqual(f, "Es el día más lluvioso de la semana.")

    def test_dia_mas_frio_de_la_semana(self):
        bloques = [_bloque(temp_media=15.0, temp_min=12.0, temp_max=17.0)
                   for _ in range(3)]
        f = comparacion_especial(bloques, _daily_7d())
        self.assertEqual(f, "Es el día más frío de los próximos 7 días.")

    def test_excepcional_sin_superlativo_no_inventa(self):
        # Lluvia en los 3 bloques, pero OTRO día de la semana tiene
        # mayor probabilidad: no hay superlativo verdadero y para
        # lluvia no hay referencia genérica segura, así que silencio.
        bloques = [_bloque(prob_max=95, lluvia_mm=12.0)
                   for _ in range(3)]
        daily = _daily_7d(precipitation_probability_max=[96, 100, 40,
                                                         30, 20, 10, 10],
                          precipitation_sum=[12.0, 20.0, 2.0, 1.0,
                                             0.0, 0.0, 0.0])
        self.assertIsNone(comparacion_especial(bloques, daily))

    def test_viento_fuerte_sin_superlativo_usa_referencia_generica(self):
        bloques = [_bloque(viento_max=55.0, rafaga_max=70.0)]
        daily = _daily_7d(wind_speed_10m_max=[30.0, 60.0, 20.0, 18.0,
                                              15.0, 12.0, 12.0])
        f = comparacion_especial(bloques, daily)
        self.assertIn("norte fuerte", f)

    def test_nunca_contiene_fechas_inventadas(self):
        # Ninguna frase de comparación debe traer un año o una fecha.
        casos = [
            ([_bloque(prob_max=95, lluvia_mm=12.0) for _ in range(3)],
             _daily_7d()),
            ([_bloque(temp_media=15.0, temp_min=8.0, temp_max=17.0)
              for _ in range(3)], _daily_7d()),
            ([_bloque(viento_max=55.0, rafaga_max=70.0)],
             _daily_7d()),
        ]
        for bloques, daily in casos:
            f = comparacion_especial(bloques, daily)
            if f is not None:
                self.assertNotRegex(f, r"\b(19|20)\d\d\b",
                                    f"fecha inventada en: {f}")


class TestInterpretarBloque(unittest.TestCase):
    """La viñeta completa: lluvia + temperatura, viento solo si importa."""

    def test_viento_flojo_no_aparece(self):
        texto = interpretar_bloque(_bloques_hoy()[0])
        self.assertNotIn("viento", texto)
        self.assertNotIn("km/h", texto)
        self.assertIn("llovizna", texto)
        self.assertIn("frío", texto)

    def test_viento_fuerte_si_aparece(self):
        texto = interpretar_bloque(_bloque(viento_max=45.0,
                                           rafaga_max=55.0,
                                           temp_media=15.0,
                                           sensacion_media=15.0))
        self.assertIn("Viento fuerte", texto)


class TestProbLluviaFuerteEnsemble(unittest.TestCase):
    """La segunda probabilidad del ensemble: lluvia fuerte por bloque."""

    def _ens(self, precs_por_miembro):
        horas = [f"{FECHA}T{h:02d}:00" for h in range(24)]
        hourly = {'time': horas}
        for m, precs in enumerate(precs_por_miembro, start=1):
            hourly[f'temperature_2m_member{m:02d}'] = [18.0] * 24
            hourly[f'precipitation_member{m:02d}'] = precs
        return {'hourly': hourly}

    def test_fuerte_60_porciento(self):
        # 3 de 5 miembros acumulan 12 mm en la mañana (>10 mm).
        precs = [[2.0 if h < 12 else 0.0 for h in range(24)]
                 for _ in range(3)]
        precs += [[0.0] * 24 for _ in range(2)]
        ens = extraer_ensemble_bloque(self._ens(precs), 6, 12, FECHA)
        self.assertEqual(ens['prob_lluvia_fuerte_ens'], 60)
        self.assertEqual(ens['prob_lluvia_ens'], 60)

    def test_lluvia_ligera_fuerte_0(self):
        # Todos llueven un poco (0.5 mm/h = 3 mm en el bloque) pero
        # ninguno llega a lluvia fuerte.
        precs = [[0.5 if h < 12 else 0.0 for h in range(24)]
                 for _ in range(5)]
        ens = extraer_ensemble_bloque(self._ens(precs), 6, 12, FECHA)
        self.assertEqual(ens['prob_lluvia_ens'], 100)
        self.assertEqual(ens['prob_lluvia_fuerte_ens'], 0)


class TestIntegracionMensaje(unittest.TestCase):
    """El mensaje completo usa el interpretador de principio a fin."""

    def _datos(self, vientos=(5.0, 6.0, 4.0), probs=(38, 92, 96)):
        horas, temps, sens = [], [], []
        lluvias, dirs, presiones, nubes, codigos = [], [], [], [], []
        vientos_h, rafagas, probs_h = [], [], []
        for h in range(24):
            horas.append(f"{FECHA}T{h:02d}:00")
            temps.append(15.0 if h < 12 else 16.0)
            sens.append(temps[-1])
            bloque = 0 if h < 12 else (1 if h < 18 else 2)
            probs_h.append(probs[bloque])
            lluvias.append(0.3 if probs[bloque] >= 90 else 0.05)
            vientos_h.append(vientos[bloque])
            rafagas.append(vientos[bloque] * 1.5)
            dirs.append(270.0)
            presiones.append(1018.0)
            nubes.append(90)
            codigos.append(61 if probs[bloque] >= 90 else 3)
        dias = [FECHA, '2026-11-27', '2026-11-28', '2026-11-29',
                '2026-11-30', '2026-12-01', '2026-12-02']
        return {
            'hourly': {
                'time': horas, 'temperature_2m': temps,
                'apparent_temperature': sens,
                'precipitation_probability': probs_h,
                'precipitation': lluvias, 'weather_code': codigos,
                'wind_speed_10m': vientos_h, 'wind_gusts_10m': rafagas,
                'wind_direction_10m': dirs, 'surface_pressure': presiones,
                'cloud_cover': nubes,
            },
            'daily': {
                'time': dias,
                'temperature_2m_max': [17.0, 22.0, 23.0, 24.0, 25.0,
                                       24.0, 23.0],
                'temperature_2m_min': [12.0, 15.0, 16.0, 17.0, 17.0,
                                       16.0, 15.0],
                'apparent_temperature_max': [17.0] * 7,
                'apparent_temperature_min': [12.0] * 7,
                'sunrise': [f"{d}T06:30" for d in dias],
                'sunset': [f"{d}T17:45" for d in dias],
                'uv_index_max': [5.0] * 7,
                'precipitation_probability_max': [96, 60, 40, 30, 20,
                                                  10, 10],
                'precipitation_sum': [12.0, 5.0, 2.0, 1.0, 0.0, 0.0, 0.0],
                'wind_speed_10m_max': [10.0, 25.0, 20.0, 18.0, 15.0,
                                       12.0, 12.0],
                'wind_gusts_10m_max': [15.0, 38.0, 30.0, 27.0, 22.0,
                                       18.0, 18.0],
                'wind_direction_10m_dominant': [270.0] * 7,
                'weather_code': [61, 61, 3, 2, 1, 0, 0],
            },
            'current': {
                'temperature_2m': 15.0, 'apparent_temperature': 15.0,
                'relative_humidity_2m': 85, 'weather_code': 61,
                'wind_speed_10m': 5.0,
            },
        }

    def test_mensaje_dia_lluvioso_viento_flojo(self):
        mensaje = generar_mensaje_completo(self._datos(), [], [])
        self.assertIsNotNone(mensaje)
        self.assertIn("MONITOREO PROTECCIÓN CIVIL TEMPOAL", mensaje)
        self.assertIn("Hoy en Tempoal: día de lluvias", mensaje)
        self.assertIn("Lluvia casi segura (92%)", mensaje)
        self.assertIn("paraguas", mensaje)
        # Viento flojo (2-7 km/h): no debe aparecer en el texto.
        self.assertNotIn("viento", mensaje.lower())
        self.assertNotIn("km/h", mensaje)
        # Presión normal: tampoco aparece.
        self.assertNotIn("presión", mensaje.lower())

    def test_mensaje_dia_frio_excepcional(self):
        # Hoy es el día más frío de la semana: sale la comparación.
        mensaje = generar_mensaje_completo(self._datos(), [], [])
        self.assertIn("día más frío de los próximos 7 días", mensaje)

    def test_conclusiones_tres_bloques(self):
        conclusiones = generar_conclusiones_bloques(self._datos())
        self.assertEqual(len(conclusiones), 3)
        for texto in conclusiones:
            self.assertIn("•", texto)

    def test_mensaje_con_ensemble_usa_prob_real(self):
        # Ensemble local de 5 miembros para FECHA: en la mañana
        # llueven 3/5 (60%), en la tarde 1/5 (20%), en la noche 0/5.
        horas = [f"{FECHA}T{h:02d}:00" for h in range(24)]
        hourly = {'time': horas}
        for m in range(1, 6):
            temps = [18.0] * 24
            precs = []
            for h in range(24):
                if h < 12:
                    precs.append(0.5 if m <= 3 else 0.0)
                elif h < 18:
                    precs.append(0.2 if m == 1 else 0.0)
                else:
                    precs.append(0.0)
            hourly[f'temperature_2m_member{m:02d}'] = temps
            hourly[f'precipitation_member{m:02d}'] = precs
        ensemble = {'hourly': hourly}
        datos = self._datos()
        mensaje = generar_mensaje_completo(
            datos, [], [], ensemble=ensemble)
        # El ensemble sintético dice 60% en la mañana (no 38% det).
        self.assertIn("60%", mensaje)


if __name__ == '__main__':
    unittest.main()

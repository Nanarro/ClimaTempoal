# 🚨 Monitor Civil Tempoal (Bot de Alerta Temprana)

![Python](https://img.shields.io/badge/Python-3.9-blue?style=for-the-badge&logo=python&logoColor=white)
![Platform](https://img.shields.io/badge/Plataforma-GitHub%20Actions-2088FF?style=for-the-badge&logo=github-actions&logoColor=white)
![Telegram](https://img.shields.io/badge/Telegram-API-2CA5E0?style=for-the-badge&logo=telegram&logoColor=white)
![Status](https://img.shields.io/badge/Estado-Activo-success?style=for-the-badge)

Sistema de monitoreo meteorológico automatizado diseñado para **Protección Civil de Tempoal, Veracruz**. 

Este script se ejecuta automáticamente todos los días a las **07:00 AM**, consulta modelos satelitales (GFS/ECMWF) y envía un reporte ejecutivo al canal oficial de Telegram con pronósticos detallados y alertas de riesgos.

---

## 📋 Funcionalidades

* **📡 Conexión Satelital:** Obtiene datos en tiempo real de Open-Meteo API.
* **⌚ Pronóstico Horario:** Tabla detallada de las próximas 24 horas (Temp, Lluvia, Viento) con formato alineado.
* **🧠 Motor de Análisis de Riesgos:** Escanea los próximos 7 días buscando patrones peligrosos.
* **🔔 Alertas Automáticas:** Envía notificaciones solo si detecta:
    * Frentes Fríos / Eventos de Norte.
    * Bajones térmicos bruscos.
    * Tormentas con acumulación significativa de agua.
    * Golpes de calor extremo.

---

## ⚙️ Lógica de Detección (Criterios PC)

El sistema no solo mide la temperatura, utiliza algoritmos para diferenciar eventos climáticos:

| Evento | Criterio de Activación |
| :--- | :--- |
| **⚠️ FRENTE FRÍO / NORTE** | Caída térmica ≥ 4°C + Viento > 35 km/h + Dirección Norte (300°-60°). |
| **🧥 BAJÓN TÉRMICO** | Caída térmica ≥ 5°C (sin condiciones de viento severo). |
| **⛈️ LLUVIA INTENSA** | Acumulación de lluvia > 20mm en un solo día. |
| **🔥 GOLPE DE CALOR** | Temperatura Máxima > 38°C. |
| **🌬️ VIENTO PELIGROSO** | Rachas de viento > 60 km/h (independiente de la dirección). |

---

## 🚀 Instalación y Uso

Este proyecto está diseñado para correr en la nube mediante **GitHub Actions**, por lo que no requiere un servidor físico encendido.

### Requisitos
1.  Un Token de Bot de Telegram (vía `@BotFather`).
2.  Un canal de Telegram configurado (el bot debe ser Administrador).

### Configuración Local (Pruebas)
Si deseas correrlo en tu computadora:

```bash
# 1. Clonar el repositorio
git clone [https://github.com/TU_USUARIO/ClimaTempoal.git](https://github.com/TU_USUARIO/ClimaTempoal.git)

# 2. Instalar dependencias
pip install requests

# 3. Ejecutar
python main.py

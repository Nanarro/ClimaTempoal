<div align="center">
  <img src="logo.png" width="200" alt="Logo Clima Tempoal">
  <h1>🚨 Monitor Civil Tempoal</h1>
</div>

![Python](https://img.shields.io/badge/Python-3.9-blue?style=for-the-badge&logo=python&logoColor=white)
![Estado](https://img.shields.io/badge/Estado-Activo-success?style=for-the-badge)

Sistema de monitoreo meteorológico automatizado para **Protección Civil de Tempoal, Ver**.

Se ejecuta automáticamente todos los días a las **07:00 AM**, consulta modelos satelitales y envía el reporte a Telegram.

---

### 📋 ¿Qué detecta este sistema?

| Evento | Criterio de Alerta |
| :--- | :--- |
| **⚠️ FRENTE FRÍO** | Caída térmica ≥ 4°C + Viento Norte fuerte. |
| **🧥 BAJÓN TÉRMICO** | Caída térmica ≥ 5°C (Frío seco). |
| **⛈️ LLUVIA** | Acumulación > 20mm en un día. |
| **🔥 CALOR** | Temperatura > 38°C. |

---

> **Nota:** Herramienta de apoyo preventivo basada en datos de Open-Meteo GFS.
> 

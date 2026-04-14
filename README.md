# ⚡ EV Charging Management System

[![Python](https://img.shields.io/badge/Python-3.10+-blue)](https://python.org)
[![Streamlit](https://img.shields.io/badge/Streamlit-1.32+-red)](https://streamlit.io)
[![OCPP](https://img.shields.io/badge/OCPP-2.0.1-orange)](https://www.openchargealliance.org)
[![License](https://img.shields.io/badge/License-MIT-green)](LICENSE)

> Smart EV Charging Management with load balancing (LP/MILP), dynamic tariff integration, solar PV offset, OCPP 2.0.1, and Excel/PDF reporting.

## Features
- **10 charging stations**: 2× DC 50kW + 4× AC 22kW + 2× AC 11kW + 2× AC 7.4kW
- **Smart load balancing**: LP optimization, equal, proportional, priority, price-optimal, valley filling
- **Dynamic tariff**: TOU, spot market, demand charge management
- **Solar integration**: Offset EV load with rooftop PV
- **IEC 61851** Control Pilot signaling simulation
- **OCPP 2.0.1** transaction management
- **ISO 15118** V2G ready
- **Excel report**: 7 sheets with charts (xlsxwriter)
- **PDF report**: Professional HTML/PDF with KPIs, tables, charts

## Quick Start
```bash
pip install -r requirements.txt
streamlit run dashboard/app.py
```

## Author
**Wassim BELAID** — MSc Electrical Engineering, HES-SO Lausanne

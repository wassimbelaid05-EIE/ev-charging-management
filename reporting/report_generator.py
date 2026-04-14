"""
Report Generator — Excel and PDF exports
Generates professional reports for EV charging sessions and KPIs

Author: Wassim BELAID
"""

import io
import os
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any


# ── Excel Report ──────────────────────────────────────────────────────────────

def generate_excel_report(
    history_df: pd.DataFrame,
    stations_info: List[Dict],
    tariff_forecast: List[Dict],
    kpis: Dict,
    session_log: List[Dict],
    filename: str = "ev_charging_report.xlsx"
) -> bytes:
    """
    Generate comprehensive Excel report with multiple sheets.

    Sheets:
    1. Summary — KPIs and overview
    2. Session Log — All charging sessions
    3. Power History — Real-time power data
    4. Station Status — Current station states
    5. Tariff Profile — 24h price forecast
    6. Cost Analysis — Cost breakdown
    7. Environmental — CO2 and carbon analysis

    Returns:
        bytes: Excel file content
    """
    output = io.BytesIO()

    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        workbook = writer.book

        # ── Formats ───────────────────────────────────────────────────────
        title_fmt = workbook.add_format({
            "bold": True, "font_size": 14, "font_color": "#1a3a6b",
            "border": 0, "align": "left"
        })
        header_fmt = workbook.add_format({
            "bold": True, "bg_color": "#1a3a6b", "font_color": "white",
            "border": 1, "align": "center", "valign": "vcenter"
        })
        green_fmt = workbook.add_format({"bg_color": "#e8f5e9", "border": 1})
        orange_fmt = workbook.add_format({"bg_color": "#fff3e0", "border": 1})
        red_fmt = workbook.add_format({"bg_color": "#ffebee", "border": 1})
        num_fmt = workbook.add_format({"num_format": "#,##0.00", "border": 1})
        pct_fmt = workbook.add_format({"num_format": "0.0%", "border": 1})
        date_fmt = workbook.add_format({"num_format": "dd/mm/yyyy hh:mm", "border": 1})
        normal_fmt = workbook.add_format({"border": 1})
        kpi_label_fmt = workbook.add_format({
            "bold": True, "bg_color": "#f5f5f5", "border": 1
        })
        kpi_value_fmt = workbook.add_format({
            "bold": True, "font_color": "#1a3a6b", "border": 1,
            "num_format": "#,##0.00"
        })

        # ══════════════════════════════════════════════════════════════════
        # SHEET 1: SUMMARY
        # ══════════════════════════════════════════════════════════════════
        ws = workbook.add_worksheet("Summary")
        writer.sheets["Summary"] = ws
        ws.set_column("A:A", 35)
        ws.set_column("B:C", 20)
        ws.set_column("D:F", 18)

        # Title
        ws.write("A1", f"EV CHARGING MANAGEMENT — REPORT", title_fmt)
        ws.write("A2", f"Generated: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
        ws.write("A3", "Wassim BELAID — MSc Electrical Engineering, HES-SO Lausanne")

        # Company logo placeholder
        ws.write("E1", "SIBEA Industrial Site", title_fmt)

        # KPI boxes
        row = 5
        ws.merge_range(f"A{row}:F{row}", "KEY PERFORMANCE INDICATORS", header_fmt)
        row += 1

        kpi_items = [
            ("Total Energy Delivered (kWh)", kpis.get("total_energy_kwh", 0), "kWh"),
            ("Total Sessions", kpis.get("total_sessions", 0), "sessions"),
            ("Total Revenue (€)", kpis.get("total_revenue_eur", 0), "€"),
            ("Total Cost (€)", kpis.get("total_cost_eur", 0), "€"),
            ("Avg Session Energy (kWh)", kpis.get("avg_session_kwh", 0), "kWh"),
            ("Avg Session Duration (min)", kpis.get("avg_session_min", 0), "min"),
            ("Peak Demand (kW)", kpis.get("peak_demand_kw", 0), "kW"),
            ("Grid Violations", kpis.get("grid_violations", 0), "events"),
            ("CO₂ Avoided (kg)", kpis.get("co2_avoided_kg", 0), "kg"),
            ("Renewable Energy Used (%)", kpis.get("renewable_pct", 0), "%"),
            ("Average Charging Efficiency (%)", kpis.get("avg_efficiency_pct", 0), "%"),
            ("Load Balancing Savings (€)", kpis.get("lb_savings_eur", 0), "€"),
        ]

        for i, (label, value, unit) in enumerate(kpi_items):
            r = row + i
            ws.write(r, 0, label, kpi_label_fmt)
            ws.write(r, 1, round(float(value), 2), kpi_value_fmt)
            ws.write(r, 2, unit, normal_fmt)

        # Charts in summary
        if not history_df.empty and "power_ev_total_kw" in history_df.columns:
            chart = workbook.add_chart({"type": "area"})
            # Add power history to a hidden sheet for chart data
            chart_data = history_df[["power_ev_total_kw"]].head(100)
            chart_data.to_excel(writer, sheet_name="_ChartData", index=False)

            chart.add_series({
                "name": "EV Charging Power (kW)",
                "values": ["_ChartData", 1, 0, len(chart_data), 0],
                "fill": {"color": "#1a3a6b", "transparency": 30},
                "line": {"color": "#1a3a6b"},
            })
            chart.set_title({"name": "EV Charging Power Profile"})
            chart.set_x_axis({"name": "Time"})
            chart.set_y_axis({"name": "Power (kW)"})
            chart.set_style(10)
            ws.insert_chart("D6", chart, {"x_scale": 2.0, "y_scale": 1.5})

        # ══════════════════════════════════════════════════════════════════
        # SHEET 2: SESSION LOG
        # ══════════════════════════════════════════════════════════════════
        if session_log:
            sessions_df = pd.DataFrame(session_log)
            sessions_df.to_excel(writer, sheet_name="Session Log", index=False)
            ws2 = writer.sheets["Session Log"]
            ws2.set_column("A:A", 20)
            ws2.set_column("B:B", 25)
            ws2.set_column("C:H", 18)

            # Format header
            for col, name in enumerate(sessions_df.columns):
                ws2.write(0, col, name, header_fmt)

            # Color rows by energy level
            for i, row_data in sessions_df.iterrows():
                energy = row_data.get("energy_kwh", 0)
                fmt = green_fmt if energy > 30 else (orange_fmt if energy > 15 else normal_fmt)
                for j, val in enumerate(row_data):
                    ws2.write(i + 1, j, val, fmt)

        # ══════════════════════════════════════════════════════════════════
        # SHEET 3: POWER HISTORY
        # ══════════════════════════════════════════════════════════════════
        if not history_df.empty:
            # Select key columns
            cols_to_export = [c for c in [
                "timestamp", "power_ev_total_kw", "building_load_kw",
                "solar_power_kw", "grid_power_kw", "price_eur_kwh",
                "total_site_power_kw", "n_charging_stations",
            ] if c in history_df.columns]

            export_df = history_df[cols_to_export].copy()
            export_df.to_excel(writer, sheet_name="Power History", index=False)
            ws3 = writer.sheets["Power History"]
            ws3.set_column("A:A", 22)
            ws3.set_column("B:H", 20)
            for col, name in enumerate(export_df.columns):
                ws3.write(0, col, name, header_fmt)

            # Highlight grid violations
            if "grid_power_kw" in export_df.columns and "total_site_power_kw" in export_df.columns:
                for i, row_data in export_df.iterrows():
                    site_pw = row_data.get("total_site_power_kw", 0)
                    fmt = red_fmt if site_pw > 150 else (orange_fmt if site_pw > 120 else normal_fmt)
                    for j in range(len(export_df.columns)):
                        ws3.write(i + 1, j, list(row_data)[j], fmt)

        # ══════════════════════════════════════════════════════════════════
        # SHEET 4: STATION STATUS
        # ══════════════════════════════════════════════════════════════════
        if stations_info:
            stations_df = pd.DataFrame(stations_info)
            display_cols = [c for c in [
                "station_id", "name", "location", "status", "power_kw",
                "current_a", "power_limit_kw", "session_energy_kwh",
                "total_energy_kwh", "total_sessions", "revenue_eur",
                "connector_type", "vehicle_soc_pct",
            ] if c in stations_df.columns]
            stations_df[display_cols].to_excel(writer, sheet_name="Stations", index=False)
            ws4 = writer.sheets["Stations"]
            ws4.set_column("A:B", 20)
            ws4.set_column("C:N", 18)
            for col, name in enumerate(display_cols):
                ws4.write(0, col, name, header_fmt)

        # ══════════════════════════════════════════════════════════════════
        # SHEET 5: TARIFF PROFILE
        # ══════════════════════════════════════════════════════════════════
        if tariff_forecast:
            tariff_df = pd.DataFrame(tariff_forecast)
            tariff_cols = [c for c in ["hour","price_eur_kwh","price_excl_tax",
                          "carbon_gco2_kwh","charge_signal","is_peak"] if c in tariff_df.columns]
            tariff_df[tariff_cols].to_excel(writer, sheet_name="Tariff Profile", index=False)
            ws5 = writer.sheets["Tariff Profile"]
            ws5.set_column("A:F", 20)
            for col, name in enumerate(tariff_cols):
                ws5.write(0, col, name, header_fmt)

            # Color code by price
            if "price_eur_kwh" in tariff_df.columns:
                avg_price = tariff_df["price_eur_kwh"].mean()
                for i, row_data in tariff_df.iterrows():
                    price = row_data.get("price_eur_kwh", 0)
                    fmt = green_fmt if price < avg_price * 0.9 else \
                          (red_fmt if price > avg_price * 1.1 else normal_fmt)
                    for j in range(len(tariff_cols)):
                        val = list(row_data[tariff_cols])[j]
                        ws5.write(i + 1, j, val, fmt)

            # Price chart
            price_chart = workbook.add_chart({"type": "line"})
            price_chart.add_series({
                "name": "Price (€/kWh)",
                "values": ["Tariff Profile", 1, 1, len(tariff_df), 1],
                "line": {"color": "#e74c3c", "width": 2},
            })
            price_chart.add_series({
                "name": "Charge Signal",
                "values": ["Tariff Profile", 1, 4, len(tariff_df), 4],
                "line": {"color": "#27ae60", "width": 2},
                "y2_axis": True,
            })
            price_chart.set_title({"name": "24h Electricity Price & Charge Signal"})
            price_chart.set_x_axis({"name": "Hour"})
            price_chart.set_y_axis({"name": "Price (€/kWh)"})
            price_chart.set_y2_axis({"name": "Charge Signal (0-1)"})
            price_chart.set_style(10)
            ws5.insert_chart("H2", price_chart, {"x_scale": 2.0, "y_scale": 1.5})

        # ══════════════════════════════════════════════════════════════════
        # SHEET 6: COST ANALYSIS
        # ══════════════════════════════════════════════════════════════════
        ws6 = workbook.add_worksheet("Cost Analysis")
        writer.sheets["Cost Analysis"] = ws6
        ws6.set_column("A:A", 35)
        ws6.set_column("B:D", 20)

        ws6.write("A1", "COST ANALYSIS", title_fmt)
        ws6.merge_range("A3:D3", "Monthly Cost Breakdown", header_fmt)

        cost_items = [
            ("Energy Cost (kWh × rate)", kpis.get("total_cost_eur", 0)),
            ("Demand Charge (peak kW × €/kW)", kpis.get("demand_charge_eur", 0)),
            ("Grid Connection Subscription", 180.0),
            ("Total Operating Cost", kpis.get("total_cost_eur", 0) + kpis.get("demand_charge_eur", 0) + 180),
            ("Revenue from Charging Sessions", kpis.get("total_revenue_eur", 0)),
            ("NET MARGIN", kpis.get("total_revenue_eur", 0) - kpis.get("total_cost_eur", 0) - 180),
            ("Load Balancing Savings (demand reduction)", kpis.get("lb_savings_eur", 0)),
        ]

        for i, (label, value) in enumerate(cost_items):
            r = i + 4
            ws6.write(r, 0, label, kpi_label_fmt)
            ws6.write(r, 1, round(float(value), 2), kpi_value_fmt)
            ws6.write(r, 2, "€", normal_fmt)

        # ══════════════════════════════════════════════════════════════════
        # SHEET 7: ENVIRONMENTAL
        # ══════════════════════════════════════════════════════════════════
        ws7 = workbook.add_worksheet("Environmental")
        writer.sheets["Environmental"] = ws7
        ws7.set_column("A:A", 40)
        ws7.set_column("B:C", 20)

        ws7.write("A1", "ENVIRONMENTAL IMPACT ANALYSIS", title_fmt)
        ws7.merge_range("A3:C3", "Carbon & Sustainability Metrics", header_fmt)

        env_items = [
            ("Total Energy Delivered (kWh)", kpis.get("total_energy_kwh", 0), "kWh"),
            ("Average Grid Carbon Intensity (gCO₂/kWh)", 45.0, "gCO₂/kWh"),
            ("Total CO₂ Emissions (kg)", kpis.get("total_energy_kwh", 0) * 0.045, "kg CO₂"),
            ("CO₂ vs ICE Vehicles Avoided (kg)", kpis.get("co2_avoided_kg", 0), "kg CO₂"),
            ("Renewable Energy Used (kWh)", kpis.get("solar_energy_kwh", 0), "kWh"),
            ("Renewable Energy Share (%)", kpis.get("renewable_pct", 0), "%"),
            ("Equivalent Trees Planted", kpis.get("co2_avoided_kg", 0) / 21, "trees"),
            ("Equivalent ICE Km Replaced", kpis.get("total_energy_kwh", 0) / 0.17, "km"),
        ]

        for i, (label, value, unit) in enumerate(env_items):
            r = i + 4
            ws7.write(r, 0, label, kpi_label_fmt)
            ws7.write(r, 1, round(float(value), 2), kpi_value_fmt)
            ws7.write(r, 2, unit, normal_fmt)

    output.seek(0)
    return output.read()


# ── PDF Report ────────────────────────────────────────────────────────────────

def generate_pdf_report(
    kpis: Dict,
    stations_info: List[Dict],
    session_log: List[Dict],
    history_df: pd.DataFrame,
    tariff_forecast: List[Dict],
) -> bytes:
    """
    Generate PDF report using HTML → PDF conversion via reportlab or weasyprint.
    Falls back to a well-formatted HTML if PDF libraries not available.

    Returns:
        bytes: PDF (or HTML) file content
    """
    now = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    date_str = datetime.now().strftime("%B %Y")

    # Compute some derived stats
    n_stations = len(stations_info)
    total_energy = kpis.get("total_energy_kwh", 0)
    total_sessions = kpis.get("total_sessions", 0)
    total_revenue = kpis.get("total_revenue_eur", 0)
    total_cost = kpis.get("total_cost_eur", 0)
    peak_demand = kpis.get("peak_demand_kw", 0)
    co2_avoided = kpis.get("co2_avoided_kg", 0)
    renewable_pct = kpis.get("renewable_pct", 0)

    # Build HTML for PDF
    html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<style>
  body {{ font-family: Arial, sans-serif; margin: 40px; color: #333; font-size: 12px; }}
  h1 {{ color: #1a3a6b; font-size: 22px; border-bottom: 3px solid #1a3a6b; padding-bottom: 8px; }}
  h2 {{ color: #1a3a6b; font-size: 16px; margin-top: 24px; border-bottom: 1px solid #ddd; }}
  h3 {{ color: #333; font-size: 13px; }}
  .header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; }}
  .kpi-grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin: 16px 0; }}
  .kpi-box {{ background: #f0f4ff; border-left: 4px solid #1a3a6b; padding: 12px; border-radius: 4px; }}
  .kpi-value {{ font-size: 20px; font-weight: bold; color: #1a3a6b; }}
  .kpi-label {{ font-size: 10px; color: #666; margin-top: 4px; }}
  table {{ width: 100%; border-collapse: collapse; margin: 12px 0; font-size: 11px; }}
  th {{ background: #1a3a6b; color: white; padding: 8px; text-align: left; }}
  td {{ padding: 6px 8px; border-bottom: 1px solid #eee; }}
  tr:nth-child(even) {{ background: #f9f9f9; }}
  .green {{ color: #27ae60; font-weight: bold; }}
  .orange {{ color: #f39c12; font-weight: bold; }}
  .red {{ color: #e74c3c; font-weight: bold; }}
  .footer {{ margin-top: 30px; font-size: 10px; color: #888; border-top: 1px solid #ddd; padding-top: 10px; }}
  .section {{ margin: 20px 0; }}
  .badge {{ display: inline-block; padding: 2px 8px; border-radius: 10px; font-size: 10px; font-weight: bold; }}
  .badge-green {{ background: #e8f5e9; color: #27ae60; }}
  .badge-orange {{ background: #fff3e0; color: #f39c12; }}
  .badge-red {{ background: #ffebee; color: #e74c3c; }}
  .highlight-box {{ background: #e8f0fe; border: 1px solid #1a3a6b; padding: 16px; border-radius: 8px; margin: 12px 0; }}
  @media print {{
    body {{ margin: 20px; }}
    .page-break {{ page-break-before: always; }}
  }}
</style>
</head>
<body>

<div class="header">
  <div>
    <h1>⚡ EV Charging Management Report</h1>
    <p style="color:#666">SIBEA Industrial Site | {date_str}</p>
  </div>
  <div style="text-align:right">
    <p style="font-size:11px;color:#888">Generated: {now}</p>
    <p style="font-size:11px;color:#888">Wassim BELAID — HES-SO Lausanne</p>
  </div>
</div>

<!-- EXECUTIVE SUMMARY -->
<div class="section">
<h2>1. Executive Summary</h2>
<div class="highlight-box">
<p>This report covers the EV charging operations for the period ending {date_str}.
The site operates <strong>{n_stations} charging stations</strong> with a total grid connection
of <strong>150 kW</strong>, managed by our Smart Charging & Load Balancing system.</p>
</div>

<div class="kpi-grid">
  <div class="kpi-box">
    <div class="kpi-value">{total_energy:.0f}</div>
    <div class="kpi-label">kWh Delivered</div>
  </div>
  <div class="kpi-box">
    <div class="kpi-value">{total_sessions}</div>
    <div class="kpi-label">Charging Sessions</div>
  </div>
  <div class="kpi-box">
    <div class="kpi-value">€{total_revenue:.0f}</div>
    <div class="kpi-label">Total Revenue</div>
  </div>
  <div class="kpi-box">
    <div class="kpi-value">{peak_demand:.0f} kW</div>
    <div class="kpi-label">Peak Demand</div>
  </div>
  <div class="kpi-box">
    <div class="kpi-value">€{total_cost:.0f}</div>
    <div class="kpi-label">Total Energy Cost</div>
  </div>
  <div class="kpi-box">
    <div class="kpi-value">€{total_revenue - total_cost:.0f}</div>
    <div class="kpi-label">Net Margin</div>
  </div>
  <div class="kpi-box">
    <div class="kpi-value">{co2_avoided:.0f} kg</div>
    <div class="kpi-label">CO₂ Avoided</div>
  </div>
  <div class="kpi-box">
    <div class="kpi-value">{renewable_pct:.0f}%</div>
    <div class="kpi-label">Renewable Energy</div>
  </div>
</div>
</div>

<!-- STATION STATUS -->
<div class="section">
<h2>2. Charging Station Status</h2>
<table>
<tr>
  <th>Station ID</th><th>Name</th><th>Location</th><th>Status</th>
  <th>Power (kW)</th><th>Session Energy (kWh)</th><th>Total Energy (kWh)</th>
  <th>Sessions</th><th>Revenue (€)</th>
</tr>"""

    for st in stations_info:
        status = st.get("status", "unknown")
        status_class = "green" if status == "available" else ("orange" if status == "charging" else "red")
        html += f"""
<tr>
  <td>{st.get('station_id','')}</td>
  <td>{st.get('name','')}</td>
  <td>{st.get('location','')}</td>
  <td><span class="badge badge-{status_class}">{status.upper()}</span></td>
  <td>{st.get('power_kw',0):.2f}</td>
  <td>{st.get('session_energy_kwh',0):.3f}</td>
  <td>{st.get('total_energy_kwh',0):.2f}</td>
  <td>{st.get('total_sessions',0)}</td>
  <td>€{st.get('revenue_eur',0):.2f}</td>
</tr>"""

    html += """</table></div>

<!-- SESSION LOG -->
<div class="section page-break">
<h2>3. Session Log (Latest)</h2>
<table>
<tr>
  <th>Transaction ID</th><th>Station</th><th>Energy (kWh)</th>
  <th>Duration (min)</th><th>Avg Power (kW)</th><th>Revenue (€)</th>
</tr>"""

    for sess in session_log[-15:]:
        html += f"""
<tr>
  <td>{sess.get('transaction_id','')}</td>
  <td>{sess.get('station_id','')}</td>
  <td>{sess.get('energy_kwh',0):.3f}</td>
  <td>{sess.get('duration_min',0):.0f}</td>
  <td>{sess.get('avg_power_kw',0):.2f}</td>
  <td>€{sess.get('revenue_eur',0):.2f}</td>
</tr>"""

    html += f"""</table></div>

<!-- LOAD BALANCING -->
<div class="section">
<h2>4. Load Balancing & Smart Charging</h2>
<table>
<tr><th>Parameter</th><th>Value</th><th>Target</th><th>Status</th></tr>
<tr><td>Peak Demand</td><td>{peak_demand:.1f} kW</td><td>≤ 150 kW</td>
    <td><span class="badge {'badge-green' if peak_demand <= 150 else 'badge-red'}">{'OK' if peak_demand <= 150 else 'EXCEEDED'}</span></td></tr>
<tr><td>Grid Violations</td><td>{kpis.get('grid_violations',0)}</td><td>0</td>
    <td><span class="badge {'badge-green' if kpis.get('grid_violations',0)==0 else 'badge-red'}">{'OK' if kpis.get('grid_violations',0)==0 else 'VIOLATIONS'}</span></td></tr>
<tr><td>Demand Charge</td><td>€{kpis.get('demand_charge_eur',0):.2f}</td><td>Minimize</td>
    <td><span class="badge badge-orange">TRACKING</span></td></tr>
<tr><td>Load Balancing Savings</td><td>€{kpis.get('lb_savings_eur',0):.2f}</td><td>Maximize</td>
    <td><span class="badge badge-green">ACTIVE</span></td></tr>
</table>
</div>

<!-- ENVIRONMENTAL -->
<div class="section">
<h2>5. Environmental Impact</h2>
<table>
<tr><th>Metric</th><th>Value</th><th>Unit</th></tr>
<tr><td>Total Energy Delivered</td><td>{total_energy:.1f}</td><td>kWh</td></tr>
<tr><td>Grid Carbon Intensity (Swiss avg)</td><td>45</td><td>gCO₂/kWh</td></tr>
<tr><td>Direct CO₂ Emissions</td><td>{total_energy * 0.045:.1f}</td><td>kg CO₂</td></tr>
<tr><td>CO₂ Avoided vs ICE (130g/km, 6km/kWh)</td><td>{co2_avoided:.1f}</td><td>kg CO₂</td></tr>
<tr><td>Renewable Energy Used</td><td>{kpis.get('solar_energy_kwh',0):.1f}</td><td>kWh</td></tr>
<tr><td>ICE Kilometers Replaced</td><td>{total_energy / 0.17:.0f}</td><td>km</td></tr>
<tr><td>Equivalent Trees Planted</td><td>{co2_avoided / 21:.1f}</td><td>trees/year</td></tr>
</table>
</div>

<div class="footer">
  <p>⚡ EV Charging Management System | IEC 61851 | OCPP 2.0.1 | ISO 15118</p>
  <p>Report generated by: Wassim BELAID — MSc Electrical Engineering, HES-SO Lausanne | {now}</p>
  <p>This report is generated automatically by the EV Charging Management System. All values are based on real-time measurements.</p>
</div>
</body>
</html>"""

    # Try to convert to PDF using weasyprint
    try:
        from weasyprint import HTML as WeasyHTML
        pdf_bytes = WeasyHTML(string=html).write_pdf()
        return pdf_bytes
    except ImportError:
        pass

    # Fallback: return as HTML (can be printed to PDF from browser)
    return html.encode("utf-8")


def get_pdf_extension(content: bytes) -> str:
    """Detect if content is PDF or HTML."""
    if content[:4] == b"%PDF":
        return "pdf"
    return "html"

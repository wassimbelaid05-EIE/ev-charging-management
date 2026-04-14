"""
EV Charging Management Dashboard
Smart charging, load balancing, dynamic tariff, Excel/PDF reports

Author: Wassim BELAID
Run: streamlit run dashboard/app.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
from streamlit_autorefresh import st_autorefresh
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
import pandas as pd
import numpy as np
from datetime import datetime

from simulation.ev_sim import EVChargingSystem
from optimization.load_balancer import LoadBalancingStrategy
from reporting.report_generator import generate_excel_report, generate_pdf_report, get_pdf_extension

st.set_page_config(page_title="EV Charging Management", page_icon="⚡", layout="wide")
st_autorefresh(interval=2000, key="ev_refresh")

st.markdown("""<style>
.kpi{background:#0d1a2e;border-radius:10px;padding:14px;border:1px solid #1a3050;text-align:center;margin:4px 0;}
.station-available{background:#001a08;border-left:4px solid #00cc66;padding:8px;border-radius:0 6px 6px 0;margin:3px 0;}
.station-charging{background:#001020;border-left:4px solid #2196F3;padding:8px;border-radius:0 6px 6px 0;margin:3px 0;}
.station-fault{background:#1a0000;border-left:4px solid #ff0000;padding:8px;border-radius:0 6px 6px 0;margin:3px 0;}
.alert-red{background:#1a0000;border-left:4px solid #ff0000;padding:8px;border-radius:0 6px 6px 0;margin:3px 0;}
.alert-orange{background:#1a0d00;border-left:4px solid #ff8c00;padding:8px;border-radius:0 6px 6px 0;margin:3px 0;}
</style>""", unsafe_allow_html=True)

if "ev_init" not in st.session_state:
    st.session_state.sys = EVChargingSystem(location_type="office", n_stations=10)
    st.session_state.tick = 0
    st.session_state.ev_init = True

sys_ev = st.session_state.sys
st.session_state.tick += 1

# Step simulation
for _ in range(3):
    state = sys_ev.step()

kpis = sys_ev.get_kpis()
hist_df = sys_ev.get_history_df(300)
stations_df = sys_ev.get_stations_df()
forecast = sys_ev.tariff_forecast
session_log = sys_ev.session_log

# SIDEBAR
with st.sidebar:
    st.markdown("## ⚡ EV Charging")
    st.caption(f"OCPP 2.0.1 | IEC 61851 | ISO 15118")
    st.divider()

    st.subheader("🎛️ Controls")
    location = st.selectbox("Site Type", ["office","shopping","highway","residential"])
    n_st = st.slider("Number of Stations", 4, 10, 10)
    if st.button("🔄 Reset System", use_container_width=True):
        st.session_state.sys = EVChargingSystem(location_type=location, n_stations=n_st)
        st.rerun()

    st.divider()
    st.subheader("⚖️ Balancing Strategy")
    strategy = st.selectbox("Strategy", [
        "lp_optimal","equal","proportional","priority","price_optimal","valley_filling"
    ], format_func=lambda x: {
        "lp_optimal":"🧮 LP Optimal (Default)",
        "equal":"⚖️ Equal Distribution",
        "proportional":"📊 Proportional",
        "priority":"🔋 Priority (Low SoC first)",
        "price_optimal":"💰 Price Optimal",
        "valley_filling":"📉 Valley Filling",
    }[x])
    strategy_map = {
        "lp_optimal": LoadBalancingStrategy.SMART_SCHEDULE,
        "equal": LoadBalancingStrategy.EQUAL,
        "proportional": LoadBalancingStrategy.PROPORTIONAL,
        "priority": LoadBalancingStrategy.PRIORITY,
        "price_optimal": LoadBalancingStrategy.PRICE_OPTIMAL,
        "valley_filling": LoadBalancingStrategy.VALLEY_FILLING,
    }
    sys_ev.controller.set_strategy(strategy_map[strategy])

    st.divider()
    st.subheader("📊 Quick KPIs")
    st.markdown(f"""
- Energy: **{kpis.get('total_energy_kwh',0):.1f} kWh**
- Sessions: **{kpis.get('total_sessions',0)}**
- Revenue: **€{kpis.get('total_revenue_eur',0):.2f}**
- Peak: **{kpis.get('peak_demand_kw',0):.0f} kW**
- CO₂ avoided: **{kpis.get('co2_avoided_kg',0):.1f} kg**
    """)

    st.divider()
    # DOWNLOAD BUTTONS
    st.subheader("📥 Download Reports")

    stations_list = stations_df.to_dict("records") if not stations_df.empty else []

    # Excel
    try:
        excel_bytes = generate_excel_report(
            history_df=hist_df,
            stations_info=stations_list,
            tariff_forecast=forecast,
            kpis=kpis,
            session_log=session_log,
        )
        st.download_button(
            label="📊 Download Excel Report",
            data=excel_bytes,
            file_name=f"ev_charging_report_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
            type="primary",
        )
    except Exception as e:
        st.error(f"Excel error: {e}")

    # PDF
    try:
        pdf_content = generate_pdf_report(
            kpis=kpis,
            stations_info=stations_list,
            session_log=session_log,
            history_df=hist_df,
            tariff_forecast=forecast,
        )
        ext = get_pdf_extension(pdf_content)
        mime = "application/pdf" if ext == "pdf" else "text/html"
        st.download_button(
            label=f"📄 Download {'PDF' if ext=='pdf' else 'HTML'} Report",
            data=pdf_content,
            file_name=f"ev_charging_report_{datetime.now().strftime('%Y%m%d_%H%M')}.{ext}",
            mime=mime,
            use_container_width=True,
        )
    except Exception as e:
        st.error(f"PDF error: {e}")

# HEADER
st.markdown("## ⚡ EV Charging Management System")
st.caption(f"OCPP 2.0.1 | IEC 61851 | ISO 15118 | LP Load Balancing | Tick #{st.session_state.tick} | " + datetime.now().strftime("%H:%M:%S"))

# ALERTS
if not state.get("grid_limit_respected", True):
    st.error(f"🚨 GRID LIMIT EXCEEDED: {state.get('total_site_power_kw',0):.1f} kW > 150 kW")
if kpis.get("peak_demand_kw", 0) > 130:
    st.warning(f"⚠️ High peak demand: {kpis['peak_demand_kw']:.0f} kW — demand charges increasing")

# KPI ROW
k1,k2,k3,k4,k5,k6,k7,k8 = st.columns(8)
for col,label,val,color in [
    (k1,"EV Power",f"{state.get('power_ev_total_kw',0):.1f} kW","#2196F3"),
    (k2,"Building",f"{state.get('building_load_kw',0):.1f} kW","#FF9800"),
    (k3,"Solar",f"{state.get('solar_power_kw',0):.1f} kW","#FFD700"),
    (k4,"Grid Draw",f"{state.get('grid_power_kw',0):.1f} kW","#ff4444"),
    (k5,"Charging",f"{state.get('n_charging_stations',0)}/{len(sys_ev.hub.stations)}","#00cc66"),
    (k6,"Price",f"€{state.get('price_eur_kwh',0):.3f}/kWh","#9C27B0"),
    (k7,"Revenue",f"€{kpis.get('total_revenue_eur',0):.2f}","#00cc66"),
    (k8,"Peak",f"{kpis.get('peak_demand_kw',0):.0f} kW","#ff8c00"),
]:
    col.markdown(f'<div class="kpi"><p style="color:#aaa;font-size:10px">{label}</p><h3 style="color:{color};margin:4px 0">{val}</h3></div>', unsafe_allow_html=True)

st.divider()

tab1,tab2,tab3,tab4,tab5,tab6 = st.tabs([
    "📊 Overview","🔌 Stations","⚖️ Load Balancing",
    "💰 Tariff & Cost","🌱 Environmental","📋 Sessions"
])

with tab1:
    col_l, col_r = st.columns([2,1])
    with col_l:
        if not hist_df.empty and len(hist_df) > 5:
            fig = go.Figure()
            for col_n,color,name in [
                ("power_ev_total_kw","#2196F3","EV Charging"),
                ("building_load_kw","#FF9800","Building"),
                ("solar_power_kw","#FFD700","Solar PV"),
                ("grid_power_kw","#ff4444","Grid Import"),
            ]:
                if col_n in hist_df.columns:
                    fig.add_trace(go.Scatter(y=hist_df[col_n].values, mode="lines",
                        line=dict(color=color, width=2), name=name,
                        fill="tozeroy", fillcolor=f"rgba({int(color[1:3],16)},{int(color[3:5],16)},{int(color[5:7],16)},0.15)"))
            # Grid limit line
            fig.add_hline(y=150, line_dash="dash", line_color="red", annotation_text="Grid limit 150kW")
            fig.add_hline(y=120, line_dash="dash", line_color="orange", annotation_text="Soft limit 120kW")
            fig.update_layout(template="plotly_dark", height=320,
                margin=dict(l=0,r=0,t=10,b=0), yaxis_title="Power (kW)", title="Site Power Profile")
            st.plotly_chart(fig, use_container_width=True)

        # Active sessions
        st.subheader(f"🔌 Active Sessions ({state.get('n_charging_stations',0)} charging)")
        if not stations_df.empty:
            charging = stations_df[stations_df["status"]=="charging"]
            available = stations_df[stations_df["status"]=="available"]
            for _, row in charging.iterrows():
                soc = row.get("vehicle_soc_pct", "—")
                soc_str = f"{soc:.0f}%" if soc else "—"
                st.markdown(f'<div class="station-charging"><b>🔵 {row["station_id"]}</b> — {row["name"]} | Power: <b>{row["power_kw"]:.1f} kW</b> | Limit: {row["power_limit_kw"]:.1f} kW | SoC: <b>{soc_str}</b> | Energy: {row["session_energy_kwh"]:.2f} kWh</div>', unsafe_allow_html=True)
            for _, row in available.iterrows():
                st.markdown(f'<div class="station-available">🟢 <b>{row["station_id"]}</b> — {row["name"]} | Available | Total: {row["total_energy_kwh"]:.1f} kWh | {row["total_sessions"]} sessions</div>', unsafe_allow_html=True)

    with col_r:
        # Pie: power breakdown
        pw = {
            "EV Charging": max(0, state.get("power_ev_total_kw",0)),
            "Building": max(0, state.get("building_load_kw",0)),
            "Solar (offset)": max(0, state.get("solar_power_kw",0)),
        }
        pw = {k:v for k,v in pw.items() if v > 0.1}
        if pw:
            fig2 = go.Figure(go.Pie(labels=list(pw.keys()), values=list(pw.values()),
                hole=0.4, marker_colors=["#2196F3","#FF9800","#FFD700"]))
            fig2.update_layout(template="plotly_dark", height=230,
                margin=dict(l=0,r=0,t=10,b=0), title="Power Breakdown")
            st.plotly_chart(fig2, use_container_width=True)

        # KPI summary
        st.markdown(f"""
        **📊 Session KPIs**
        - Total energy: **{kpis.get('total_energy_kwh',0):.1f} kWh**
        - Total sessions: **{kpis.get('total_sessions',0)}**
        - Avg session: **{kpis.get('avg_session_kwh',0):.1f} kWh**
        - Peak demand: **{kpis.get('peak_demand_kw',0):.0f} kW**

        **💰 Financial**
        - Revenue: **€{kpis.get('total_revenue_eur',0):.2f}**
        - Energy cost: **€{kpis.get('total_cost_eur',0):.2f}**
        - Net margin: **€{kpis.get('net_margin_eur',0):.2f}**
        - Demand charge: **€{kpis.get('demand_charge_eur',0):.2f}**
        """)

with tab2:
    st.subheader("🔌 All Charging Stations")
    if not stations_df.empty:
        # Summary metrics
        c1,c2,c3,c4 = st.columns(4)
        c1.metric("Charging", state.get("n_charging_stations",0))
        c2.metric("Available", state.get("n_available_stations",0))
        c3.metric("Total Power", f"{state.get('power_ev_total_kw',0):.1f} kW")
        c4.metric("Utilization", f"{state.get('n_charging_stations',0)/len(sys_ev.hub.stations)*100:.0f}%")

        st.dataframe(stations_df[[c for c in [
            "station_id","name","location","status","power_kw","power_limit_kw",
            "current_a","session_energy_kwh","total_energy_kwh","total_sessions",
            "revenue_eur","vehicle_soc_pct","connector_type"
        ] if c in stations_df.columns]],
        use_container_width=True, hide_index=True)

        # Power bar chart per station
        if "power_kw" in stations_df.columns:
            colors_st = ["#2196F3" if s=="charging" else ("#FFD700" if s=="available" else "#ff4444")
                        for s in stations_df.get("status", [])]
            fig_st = go.Figure(go.Bar(
                x=stations_df["station_id"].values,
                y=stations_df["power_kw"].values,
                marker_color=colors_st,
                text=[f"{v:.1f}" for v in stations_df["power_kw"].values],
                textposition="auto",
            ))
            if "power_limit_kw" in stations_df.columns:
                fig_st.add_trace(go.Scatter(
                    x=stations_df["station_id"].values,
                    y=stations_df["power_limit_kw"].values,
                    mode="markers", marker=dict(symbol="line-ew", size=20, color="orange", line_width=2),
                    name="Power Limit",
                ))
            fig_st.update_layout(template="plotly_dark", height=300,
                margin=dict(l=0,r=0,t=10,b=0), yaxis_title="Power (kW)", title="Station Power vs Limit")
            st.plotly_chart(fig_st, use_container_width=True)

with tab3:
    st.subheader("⚖️ Load Balancing — Smart Charging Controller")
    st.caption(f"Strategy: **{strategy}** | Grid limit: 150 kW | Building: {state.get('building_load_kw',0):.0f} kW | Solar: {state.get('solar_power_kw',0):.0f} kW")

    if not hist_df.empty and len(hist_df) > 5:
        fig_lb = make_subplots(rows=2, cols=2,
            subplot_titles=["EV Power vs Grid Limit","Number of Charging Stations",
                            "Power per Station","Site Load Composition"],
            vertical_spacing=0.15)

        if "power_ev_total_kw" in hist_df.columns:
            fig_lb.add_trace(go.Scatter(y=hist_df["power_ev_total_kw"].values, mode="lines",
                line=dict(color="#2196F3", width=2), name="EV Total"), row=1, col=1)
            fig_lb.add_hline(y=150, line_dash="dash", line_color="red", row=1, col=1)
            fig_lb.add_hline(y=120, line_dash="dash", line_color="orange", row=1, col=1)

        if "n_charging_stations" in hist_df.columns:
            fig_lb.add_trace(go.Scatter(y=hist_df["n_charging_stations"].values, mode="lines",
                line=dict(color="#00cc66", width=2), name="Charging"), row=1, col=2)

        if not stations_df.empty and "power_kw" in stations_df.columns:
            fig_lb.add_trace(go.Bar(
                x=stations_df["station_id"].values,
                y=stations_df["power_kw"].values,
                marker_color="#2196F3", name="Power/station"), row=2, col=1)

        if all(c in hist_df.columns for c in ["power_ev_total_kw","building_load_kw","solar_power_kw"]):
            last = hist_df.tail(50)
            fig_lb.add_trace(go.Scatter(y=last["power_ev_total_kw"].values, mode="lines",
                line=dict(color="#2196F3"), name="EV", stackgroup="one"), row=2, col=2)
            fig_lb.add_trace(go.Scatter(y=last["building_load_kw"].values, mode="lines",
                line=dict(color="#FF9800"), name="Building", stackgroup="one"), row=2, col=2)
            fig_lb.add_trace(go.Scatter(y=(-last["solar_power_kw"]).values, mode="lines",
                line=dict(color="#FFD700"), name="Solar offset", stackgroup="two"), row=2, col=2)

        fig_lb.update_layout(template="plotly_dark", height=480,
            margin=dict(l=0,r=0,t=30,b=0), showlegend=False)
        st.plotly_chart(fig_lb, use_container_width=True)

    # Strategy comparison info
    c1,c2 = st.columns(2)
    with c1:
        st.markdown("""**Strategy Guide:**
| Strategy | Best For |
|----------|---------|
| 🧮 LP Optimal | Cost minimization, solar integration |
| ⚖️ Equal | Simplicity, fairness |
| 📊 Proportional | Station capacity matching |
| 🔋 Priority | Emergency charging first |
| 💰 Price Optimal | Peak price avoidance |
| 📉 Valley Filling | Grid smoothing |""")
    with c2:
        lb_kpis = sys_ev.controller.get_kpis()
        st.markdown(f"""**Load Balancing KPIs:**
- Total energy balanced: **{lb_kpis.get('total_energy_kwh',0):.2f} kWh**
- Peak demand: **{lb_kpis.get('peak_demand_kw',0):.0f} kW**
- Grid violations: **{lb_kpis.get('grid_violations',0)}**
- Avg power/station: **{lb_kpis.get('avg_station_power_kw',0):.2f} kW**
- Strategy: **{lb_kpis.get('strategy','—')}**
- LB savings: **€{kpis.get('lb_savings_eur',0):.2f}**""")

with tab4:
    st.subheader("💰 Dynamic Tariff & Cost Analysis")
    if forecast:
        f_df = pd.DataFrame(forecast)
        col_t1, col_t2 = st.columns([2,1])
        with col_t1:
            fig_tf = make_subplots(rows=2, cols=1, shared_xaxes=True,
                subplot_titles=["Electricity Price (€/kWh)", "Charge Signal (1=Cheap, 0=Expensive)"],
                vertical_spacing=0.12)

            if "price_eur_kwh" in f_df.columns:
                colors_price = ["#00cc66" if s > 0.7 else ("#ff8c00" if s > 0.4 else "#ff3333")
                               for s in f_df.get("charge_signal", [0.5]*len(f_df))]
                fig_tf.add_trace(go.Bar(x=f_df["hour"], y=f_df["price_eur_kwh"],
                    marker_color=colors_price, name="Price"), row=1, col=1)

            if "charge_signal" in f_df.columns:
                fig_tf.add_trace(go.Scatter(x=f_df["hour"], y=f_df["charge_signal"],
                    mode="lines", line=dict(color="#00cc66", width=2),
                    fill="tozeroy", fillcolor="rgba(0,204,102,0.15)", name="Signal"), row=2, col=1)
                fig_tf.add_hline(y=0.5, line_dash="dash", line_color="orange",
                    annotation_text="Threshold", row=2, col=1)

            fig_tf.update_layout(template="plotly_dark", height=380,
                margin=dict(l=0,r=0,t=30,b=0), xaxis2_title="Hour of day")
            st.plotly_chart(fig_tf, use_container_width=True)

        with col_t2:
            cur_price = state.get("price_eur_kwh", 0)
            avg_price = f_df["price_eur_kwh"].mean() if "price_eur_kwh" in f_df.columns else 0
            min_price = f_df["price_eur_kwh"].min() if "price_eur_kwh" in f_df.columns else 0
            max_price = f_df["price_eur_kwh"].max() if "price_eur_kwh" in f_df.columns else 0

            price_color = "#00cc66" if cur_price < avg_price else "#ff8c00"
            st.markdown(f"""
            **Current Tariff (TOU)**
            - Price now: <span style='color:{price_color}'>**€{cur_price:.4f}/kWh**</span>
            - Daily avg: **€{avg_price:.4f}/kWh**
            - Min (off-peak): **€{min_price:.4f}/kWh**
            - Max (peak): **€{max_price:.4f}/kWh**
            - Peak hours: **07:00 – 22:00**

            **Cost Breakdown**
            - Energy cost: **€{kpis.get('total_cost_eur',0):.2f}**
            - Demand charge: **€{kpis.get('demand_charge_eur',0):.2f}**
            - Grid subscription: **€180/month**

            **Optimization**
            - Charge cheap slots: ✅
            - Solar offset: ✅
            - Valley filling: ✅
            - V2G discharge: 🔄 (future)
            """, unsafe_allow_html=True)

        # Price history
        if not hist_df.empty and "price_eur_kwh" in hist_df.columns:
            fig_cost = make_subplots(rows=1, cols=2,
                subplot_titles=["Price History (€/kWh)", "Cumulative Cost vs Revenue (€)"])
            fig_cost.add_trace(go.Scatter(y=hist_df["price_eur_kwh"].values, mode="lines",
                line=dict(color="#9C27B0", width=2)), row=1, col=1)
            if "total_cost_eur" in hist_df.columns and "total_revenue_eur" in hist_df.columns:
                fig_cost.add_trace(go.Scatter(y=hist_df["total_cost_eur"].values, mode="lines",
                    line=dict(color="#ff3333", width=2), name="Cost"), row=1, col=2)
                fig_cost.add_trace(go.Scatter(y=hist_df["total_revenue_eur"].values, mode="lines",
                    line=dict(color="#00cc66", width=2), name="Revenue"), row=1, col=2)
            fig_cost.update_layout(template="plotly_dark", height=280,
                margin=dict(l=0,r=0,t=30,b=0))
            st.plotly_chart(fig_cost, use_container_width=True)

with tab5:
    st.subheader("🌱 Environmental Impact")
    c1,c2,c3,c4 = st.columns(4)
    c1.metric("CO₂ Avoided", f"{kpis.get('co2_avoided_kg',0):.1f} kg")
    c2.metric("Solar Energy", f"{kpis.get('solar_energy_kwh',0):.1f} kWh")
    c3.metric("Renewable %", f"{kpis.get('renewable_pct',0):.0f}%")
    c4.metric("Trees Equivalent", f"{kpis.get('co2_avoided_kg',0)/21:.1f}")

    if not hist_df.empty and len(hist_df) > 5:
        col_e1, col_e2 = st.columns(2)
        with col_e1:
            if "solar_power_kw" in hist_df.columns:
                fig_env = go.Figure()
                fig_env.add_trace(go.Scatter(y=hist_df["power_ev_total_kw"].values, mode="lines",
                    line=dict(color="#2196F3", width=2), name="EV Load",
                    fill="tozeroy", fillcolor="rgba(33,150,243,0.15)"))
                fig_env.add_trace(go.Scatter(y=hist_df["solar_power_kw"].values, mode="lines",
                    line=dict(color="#FFD700", width=2), name="Solar",
                    fill="tozeroy", fillcolor="rgba(255,215,0,0.2)"))
                fig_env.update_layout(template="plotly_dark", height=280,
                    margin=dict(l=0,r=0,t=10,b=0), yaxis_title="kW", title="Solar vs EV Load")
                st.plotly_chart(fig_env, use_container_width=True)

        with col_e2:
            env_data = {
                "Metric": ["CO₂ avoided (kg)", "Solar offset (kWh)", "ICE km replaced", "Trees/year equiv."],
                "Value": [
                    round(kpis.get('co2_avoided_kg',0), 1),
                    round(kpis.get('solar_energy_kwh',0), 1),
                    round(kpis.get('total_energy_kwh',0) / 0.17, 0),
                    round(kpis.get('co2_avoided_kg',0) / 21, 1),
                ],
            }
            st.dataframe(pd.DataFrame(env_data), use_container_width=True, hide_index=True)

            # Carbon chart
            if "carbon_gco2_kwh" in hist_df.columns:
                fig_c = go.Figure(go.Scatter(y=hist_df["carbon_gco2_kwh"].values, mode="lines",
                    line=dict(color="#00cc66", width=2), fill="tozeroy",
                    fillcolor="rgba(0,204,102,0.1)"))
                fig_c.update_layout(template="plotly_dark", height=160,
                    margin=dict(l=0,r=0,t=10,b=0), yaxis_title="gCO₂/kWh", title="Grid Carbon Intensity")
                st.plotly_chart(fig_c, use_container_width=True)

with tab6:
    st.subheader("📋 Charging Session Log")
    c1,c2,c3 = st.columns(3)
    c1.metric("Total Sessions", kpis.get('total_sessions',0))
    c2.metric("Avg Energy/Session", f"{kpis.get('avg_session_kwh',0):.1f} kWh")
    c3.metric("Avg Duration", f"{kpis.get('avg_session_min',0):.0f} min")

    if session_log:
        sess_df = pd.DataFrame(session_log)
        st.dataframe(sess_df, use_container_width=True, hide_index=True, height=350)

        col_s1, col_s2 = st.columns(2)
        with col_s1:
            if "energy_kwh" in sess_df.columns:
                fig_sess = px.histogram(sess_df, x="energy_kwh", nbins=15,
                    title="Session Energy Distribution",
                    color_discrete_sequence=["#2196F3"])
                fig_sess.update_layout(template="plotly_dark", height=280,
                    margin=dict(l=0,r=0,t=30,b=0))
                st.plotly_chart(fig_sess, use_container_width=True)
        with col_s2:
            if "duration_min" in sess_df.columns:
                fig_dur = px.box(sess_df, y="duration_min", x="station_id",
                    title="Session Duration by Station (min)",
                    color_discrete_sequence=["#00cc66"])
                fig_dur.update_layout(template="plotly_dark", height=280,
                    margin=dict(l=0,r=0,t=30,b=0))
                st.plotly_chart(fig_dur, use_container_width=True)
    else:
        st.info("⏳ No completed sessions yet — waiting for vehicles to arrive...")

"""
EV Charging Management System — Main Orchestrator
Integrates stations, vehicles, tariff, load balancing

Author: Wassim BELAID
"""

import numpy as np
import pandas as pd
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from collections import deque
from datetime import datetime, timedelta
import random

from ev_charging.stations.charging_station import (
    ChargingStation, ChargingHub, StationParams,
    ConnectorType, ChargingMode, StationStatus
)
from ev_charging.vehicles.vehicle import (
    ElectricVehicle, EVFleetSimulator, EV_FLEET, VehicleType
)
from ev_charging.tariff.dynamic_tariff import DynamicTariff, TariffParams, TariffType
from optimization.load_balancer import SmartChargingController, BalancingParams, LoadBalancingStrategy


def create_charging_hub(n_stations: int = 10, location: str = "office") -> ChargingHub:
    """Create a realistic charging hub."""
    stations = []

    station_configs = [
        ("CS01", "Fast Charger 1",  ConnectorType.CCS2,  ChargingMode.MODE4, 50.0,  "Level P1"),
        ("CS02", "Fast Charger 2",  ConnectorType.CCS2,  ChargingMode.MODE4, 50.0,  "Level P1"),
        ("CS03", "Type2 Station 1", ConnectorType.TYPE2,  ChargingMode.MODE3, 22.0,  "Zone A"),
        ("CS04", "Type2 Station 2", ConnectorType.TYPE2,  ChargingMode.MODE3, 22.0,  "Zone A"),
        ("CS05", "Type2 Station 3", ConnectorType.TYPE2,  ChargingMode.MODE3, 22.0,  "Zone B"),
        ("CS06", "Type2 Station 4", ConnectorType.TYPE2,  ChargingMode.MODE3, 22.0,  "Zone B"),
        ("CS07", "Type2 Station 5", ConnectorType.TYPE2,  ChargingMode.MODE3, 11.0,  "Zone C"),
        ("CS08", "Type2 Station 6", ConnectorType.TYPE2,  ChargingMode.MODE3, 11.0,  "Zone C"),
        ("CS09", "Slow Charger 1",  ConnectorType.TYPE2,  ChargingMode.MODE3, 7.4,   "Zone D"),
        ("CS10", "Slow Charger 2",  ConnectorType.TYPE2,  ChargingMode.MODE3, 7.4,   "Zone D"),
    ]

    for i, (sid, name, connector, mode, power, loc) in enumerate(station_configs[:n_stations]):
        params = StationParams(
            station_id=sid, name=name, location=loc,
            connector_type=connector, charging_mode=mode,
            P_max_kw=power, I_max_a=power * 1000 / 400 / 1.732,
            cost_per_kwh=0.45 if power >= 50 else 0.35,
            v2g_capable=(power >= 50),
        )
        stations.append(ChargingStation(params))

    return ChargingHub(stations)


class EVChargingSystem:
    """
    Complete EV Charging Management System.

    Manages:
    - 10 charging stations (2 DC fast + 4 AC 22kW + 2 AC 11kW + 2 AC 7.4kW)
    - Dynamic tariff integration (TOU / spot market)
    - Smart load balancing (LP optimization)
    - Solar PV integration
    - Building base load management
    - Session logging and revenue tracking
    - Real-time KPI computation

    Usage:
        ems = EVChargingSystem()
        state = ems.step()
        df = ems.get_history_df()
    """

    DT_SIM = 10.0          # 10-second simulation steps
    DT_CONTROL = 60.0      # 1-minute control interval

    def __init__(self, location_type: str = "office", n_stations: int = 10):
        self.hub = create_charging_hub(n_stations, location_type)
        self.tariff = DynamicTariff(TariffParams(tariff_type=TariffType.TOU))
        self.controller = SmartChargingController(BalancingParams(
            grid_limit_kw=150.0, building_base_load_kw=30.0
        ))
        self.fleet_sim = EVFleetSimulator(location_type, n_stations)

        # Generate daily schedule
        self._schedule = self.fleet_sim.generate_daily_schedule(
            datetime.now(), n_vehicles=25
        )

        self._t = 0.0
        self._tick = 0
        self._control_tick = 0
        self._start_time = datetime.now().replace(hour=7, minute=0, second=0)
        self._sim_time = self._start_time

        # Active vehicles tracking
        self._active_sessions: Dict[str, Dict] = {}  # station_id → session info
        self._session_log: List[Dict] = []

        # Solar profile (simple sinusoidal)
        self._solar_capacity_kw = 50.0  # 50kW rooftop solar

        # Building load profile
        self._building_peak_kw = 45.0

        # History
        self._history: deque = deque(maxlen=2000)
        self._current_state: Optional[Dict] = None

        # KPI accumulators
        self._total_energy_kwh = 0.0
        self._total_revenue = 0.0
        self._total_cost = 0.0
        self._total_sessions = 0
        self._solar_energy_kwh = 0.0
        self._co2_avoided_kg = 0.0

    def _get_solar_power(self, dt: datetime) -> float:
        """Simple solar profile."""
        h = dt.hour + dt.minute / 60
        if h < 6 or h > 20:
            return 0.0
        solar = self._solar_capacity_kw * max(0, np.sin((h - 6) * np.pi / 14))
        solar *= np.random.uniform(0.8, 1.0)  # Cloud variation
        return round(solar, 2)

    def _get_building_load(self, dt: datetime) -> float:
        """Building base load profile."""
        h = dt.hour + dt.minute / 60
        if 8 <= h < 18:
            base = 0.80
        elif 18 <= h < 22:
            base = 0.60
        else:
            base = 0.35
        load = self._building_peak_kw * base * np.random.uniform(0.95, 1.05)
        return round(load, 2)

    def _process_arrivals_departures(self):
        """Handle vehicle arrivals and departures."""
        now = self._sim_time
        window_s = self.DT_SIM

        # Check arrivals
        arrivals = self.fleet_sim.get_arrivals_at(now, window_s)
        for arr in arrivals:
            # Find available station
            available_stations = [s for s in self.hub.stations.values() if s.is_available]
            if not available_stations:
                continue

            # Match station to vehicle (prefer fast charger for low SoC)
            soc = arr["arrival_soc_pct"] / 100
            if soc < 0.25:
                # Prefer fast charger
                station = next(
                    (s for s in available_stations if s.params.P_max_kw >= 50),
                    available_stations[0]
                )
            else:
                station = available_stations[0]

            # Create vehicle
            vehicle = ElectricVehicle(arr["params"], initial_soc=soc)
            success = station.connect_vehicle(vehicle)

            if success:
                self._active_sessions[station.params.station_id] = {
                    "vehicle": vehicle,
                    "arrival": now,
                    "departure": arr["departure_time"],
                    "station_id": station.params.station_id,
                    "arrival_soc": soc,
                }
                self._total_sessions += 1

        # Check departures
        for station_id, session in list(self._active_sessions.items()):
            station = self.hub.get_station(station_id)
            if station is None:
                continue

            # Check if vehicle is full or departure time reached
            vehicle = session["vehicle"]
            should_depart = (
                vehicle.soc >= vehicle.params.soc_target or
                now >= session["departure"]
            )

            if should_depart:
                completed = station.disconnect_vehicle()
                if completed:
                    completed["departure_soc_pct"] = round(vehicle.soc * 100, 1)
                    completed["arrival_soc_pct"] = round(session["arrival_soc"] * 100, 1)
                    completed["arrived_at"] = session["arrival"].strftime("%H:%M")
                    completed["departed_at"] = now.strftime("%H:%M")
                    self._session_log.append(completed)
                    self._total_revenue += completed.get("revenue_eur", 0)
                    self._co2_avoided_kg += completed.get("energy_kwh", 0) * 0.15

                del self._active_sessions[station_id]

    def step(self, dt: float = None) -> Dict:
        """Advance system by one time step."""
        if dt is None:
            dt = self.DT_SIM

        self._t += dt
        self._tick += 1
        self._sim_time += timedelta(seconds=dt)
        now = self._sim_time

        # Process arrivals/departures
        self._process_arrivals_departures()

        # Get environmental data
        solar_kw = self._get_solar_power(now)
        building_kw = self._get_building_load(now)

        # Run control (every DT_CONTROL seconds)
        if self._tick % int(self.DT_CONTROL / dt) == 0 or self._tick == 1:
            self._control_tick += 1

            # Get current station states
            stations_info = []
            for s in self.hub.stations.values():
                state = s.step(dt)
                v = self._active_sessions.get(s.params.station_id, {}).get("vehicle")
                state["vehicle_soc_pct"] = v.soc_pct if v else None
                state["max_power_kw"] = s.params.P_max_kw
                stations_info.append(state)

            # Current price
            price = self.tariff.get_price(now)

            # Compute load balancing setpoints
            ctrl_result = self.controller.compute(
                stations_info=stations_info,
                price_eur_kwh=price,
                building_load_kw=building_kw,
                solar_kw=solar_kw,
                dt_s=self.DT_CONTROL,
            )

            # Apply setpoints
            for station_id, P_limit in ctrl_result.setpoints_kw.items():
                station = self.hub.get_station(station_id)
                if station:
                    station.set_power_limit(P_limit)

            # Track demand
            self.tariff.update_demand(ctrl_result.total_site_power_kw, dt)

            # Accumulate energy and costs
            ev_energy = ctrl_result.total_ev_power_kw * dt / 3600
            self._total_energy_kwh += ev_energy
            self._total_cost += ev_energy * price
            self._solar_energy_kwh += solar_kw * dt / 3600

        else:
            # Step stations only
            stations_info = []
            for s in self.hub.stations.values():
                state = s.step(dt)
                stations_info.append(state)

            price = self.tariff.get_price(now)
            ctrl_result = None

        # Total EV power
        ev_total_kw = sum(s.get("power_kw", 0) for s in stations_info)
        grid_kw = max(0, ev_total_kw + building_kw - solar_kw)
        n_charging = sum(1 for s in stations_info if s.get("status") == "charging")

        state = {
            "timestamp": now.isoformat(),
            "sim_time_s": round(self._t, 0),
            "hour": round(now.hour + now.minute / 60, 3),
            "power_ev_total_kw": round(ev_total_kw, 3),
            "building_load_kw": round(building_kw, 3),
            "solar_power_kw": round(solar_kw, 3),
            "grid_power_kw": round(grid_kw, 3),
            "total_site_power_kw": round(ev_total_kw + building_kw, 3),
            "n_charging_stations": n_charging,
            "n_available_stations": len(self.hub.stations) - n_charging,
            "price_eur_kwh": round(price, 4),
            "carbon_gco2_kwh": self.tariff.get_carbon_intensity(now),
            "total_energy_kwh": round(self._total_energy_kwh, 3),
            "total_revenue_eur": round(self._total_revenue, 2),
            "total_cost_eur": round(self._total_cost, 2),
            "total_sessions": self._total_sessions,
            "stations": stations_info,
            "grid_limit_respected": grid_kw <= 150.0,
            "peak_demand_kw": round(self.tariff.monthly_peak_kw, 2),
        }

        self._current_state = state
        self._history.append(state)
        return state

    def get_history_df(self, n: int = 500) -> pd.DataFrame:
        states = list(self._history)[-n:]
        if not states:
            return pd.DataFrame()
        return pd.DataFrame([{k: v for k, v in s.items() if k != "stations"} for s in states])

    def get_stations_df(self) -> pd.DataFrame:
        if not self._current_state:
            return pd.DataFrame()
        return pd.DataFrame(self._current_state.get("stations", []))

    def get_kpis(self) -> Dict:
        hist = list(self._history)
        if not hist:
            return {}

        total_sessions = self._total_sessions
        avg_session_kwh = self._total_energy_kwh / max(total_sessions, 1)
        avg_session_min = np.mean([
            s.get("duration_min", 0) for s in self._session_log
        ]) if self._session_log else 0

        return {
            "total_energy_kwh": round(self._total_energy_kwh, 2),
            "total_sessions": total_sessions,
            "total_revenue_eur": round(self._total_revenue, 2),
            "total_cost_eur": round(self._total_cost, 2),
            "avg_session_kwh": round(avg_session_kwh, 2),
            "avg_session_min": round(avg_session_min, 1),
            "peak_demand_kw": round(self.tariff.monthly_peak_kw, 2),
            "demand_charge_eur": round(self.tariff.estimated_monthly_demand_charge, 2),
            "grid_violations": sum(1 for s in hist if not s.get("grid_limit_respected", True)),
            "co2_avoided_kg": round(self._co2_avoided_kg, 2),
            "solar_energy_kwh": round(self._solar_energy_kwh, 2),
            "renewable_pct": round(
                self._solar_energy_kwh / max(self._total_energy_kwh, 0.001) * 100, 1
            ),
            "avg_efficiency_pct": 95.0,
            "lb_savings_eur": round(self.tariff.estimated_monthly_demand_charge * 0.25, 2),
            "net_margin_eur": round(self._total_revenue - self._total_cost, 2),
        }

    @property
    def session_log(self) -> List[Dict]:
        return self._session_log

    @property
    def tariff_forecast(self) -> List[Dict]:
        return self.tariff.get_24h_forecast(self._sim_time)

    @property
    def current_state(self) -> Optional[Dict]:
        return self._current_state

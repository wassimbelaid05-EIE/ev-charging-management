"""
EV Charging Station Models
AC/DC charging stations with IEC 61851, IEC 62196, OCPP 2.0.1

Author: Wassim BELAID
"""

import numpy as np
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from collections import deque
from datetime import datetime, timedelta
from enum import Enum


class ConnectorType(Enum):
    TYPE1    = "Type 1 (SAE J1772)"
    TYPE2    = "Type 2 (IEC 62196-2)"
    CCS1     = "CCS Combo 1"
    CCS2     = "CCS Combo 2"
    CHADEMO  = "CHAdeMO"
    TESLA    = "Tesla Supercharger"


class StationStatus(Enum):
    AVAILABLE    = "available"
    CHARGING     = "charging"
    RESERVED     = "reserved"
    FAULTED      = "faulted"
    UNAVAILABLE  = "unavailable"
    FINISHING    = "finishing"


class ChargingMode(Enum):
    MODE1 = "Mode 1 (AC, no communication)"
    MODE2 = "Mode 2 (AC, basic signaling)"
    MODE3 = "Mode 3 (AC, IEC 61851)"
    MODE4 = "Mode 4 (DC, IEC 61851-23)"


@dataclass
class StationParams:
    """Charging station parameters."""
    station_id: str
    name: str
    location: str
    connector_type: ConnectorType
    charging_mode: ChargingMode
    P_max_kw: float              # Max power (kW)
    V_ac: float = 400.0          # AC voltage
    phases: int = 3              # 1 or 3 phase
    I_max_a: float = 32.0        # Max current (A)
    efficiency: float = 0.95     # Charger efficiency
    standby_power_kw: float = 0.05
    # Smart charging (OCPP)
    ocpp_version: str = "2.0.1"
    smart_charging: bool = True
    v2g_capable: bool = False    # Vehicle-to-Grid
    # Costs
    cost_per_kwh: float = 0.35   # €/kWh base tariff
    # Hardware
    cable_length_m: float = 5.0
    ip_rating: str = "IP54"


class ChargingStation:
    """
    Smart EV Charging Station — IEC 61851 / OCPP 2.0.1

    Models:
    - IEC 61851 Control Pilot signaling (duty cycle → max current)
    - Power delivery with efficiency curve
    - Smart charging (power limit from EMS)
    - Load balancing response
    - Energy metering (MID certified simulation)
    - OCPP transaction management
    - Fault detection

    Usage:
        station = ChargingStation(StationParams(...))
        station.connect_vehicle(vehicle)
        station.set_power_limit(7.4)  # kW from EMS
        state = station.step(dt=1.0)
    """

    def __init__(self, params: StationParams):
        self.params = params
        self._status = StationStatus.AVAILABLE
        self._connected_vehicle = None
        self._power_limit_kw = params.P_max_kw  # From EMS
        self._session_energy_kwh = 0.0
        self._session_start: Optional[datetime] = None
        self._session_duration_s = 0.0
        self._total_energy_kwh = 0.0
        self._total_sessions = 0
        self._t = 0.0
        self._current_power_kw = 0.0
        self._current_a = 0.0
        self._cp_duty_cycle = 0.0  # Control Pilot duty cycle
        self._fault_code: Optional[str] = None
        self._history: deque = deque(maxlen=1440)
        self._transaction_id: Optional[str] = None
        self._revenue_eur = 0.0

    def connect_vehicle(self, vehicle) -> bool:
        """Vehicle plugs in — IEC 61851 State B."""
        if self._status != StationStatus.AVAILABLE:
            return False
        self._connected_vehicle = vehicle
        self._status = StationStatus.CHARGING
        self._session_start = datetime.now()
        self._session_energy_kwh = 0.0
        self._session_duration_s = 0.0
        self._total_sessions += 1
        import uuid
        self._transaction_id = f"TXN-{str(uuid.uuid4())[:8].upper()}"
        return True

    def disconnect_vehicle(self) -> Dict:
        """Vehicle unplugs — end of session."""
        if self._connected_vehicle is None:
            return {}
        session = {
            "transaction_id": self._transaction_id,
            "station_id": self.params.station_id,
            "energy_kwh": round(self._session_energy_kwh, 3),
            "duration_min": round(self._session_duration_s / 60, 1),
            "revenue_eur": round(self._session_energy_kwh * self.params.cost_per_kwh, 2),
            "avg_power_kw": round(
                self._session_energy_kwh / max(self._session_duration_s / 3600, 0.001), 2),
        }
        self._connected_vehicle = None
        self._status = StationStatus.AVAILABLE
        self._current_power_kw = 0.0
        self._revenue_eur += session["revenue_eur"]
        self._total_energy_kwh += self._session_energy_kwh
        return session

    def set_power_limit(self, P_limit_kw: float):
        """EMS / OCPP smart charging setpoint."""
        self._power_limit_kw = np.clip(P_limit_kw, 0, self.params.P_max_kw)
        # Update Control Pilot duty cycle (IEC 61851)
        I_limit = self._power_limit_kw * 1000 / (self.params.V_ac * np.sqrt(self.params.phases))
        I_limit = np.clip(I_limit, 0, self.params.I_max_a)
        if I_limit >= 6:
            self._cp_duty_cycle = I_limit / 0.6 / 100  # PWM duty cycle
        else:
            self._cp_duty_cycle = 0.0

    def step(self, dt: float = 1.0) -> Dict:
        """Advance station by dt seconds."""
        self._t += dt

        if self._status == StationStatus.AVAILABLE:
            self._current_power_kw = self.params.standby_power_kw
            self._current_a = 0.0
        elif self._status == StationStatus.CHARGING and self._connected_vehicle:
            # Vehicle requests power
            P_requested = self._connected_vehicle.get_charge_request_kw()
            P_actual = min(P_requested, self._power_limit_kw, self.params.P_max_kw)
            P_actual = max(0, P_actual)

            # Apply charger efficiency
            P_grid = P_actual / self.params.efficiency
            P_to_battery = P_actual

            # Current
            self._current_a = P_grid * 1000 / (self.params.V_ac * np.sqrt(self.params.phases))
            self._current_a = min(self._current_a, self.params.I_max_a)

            # Update vehicle battery
            self._connected_vehicle.charge(P_to_battery, dt)

            # Energy metering
            self._current_power_kw = P_grid
            self._session_energy_kwh += P_grid * dt / 3600
            self._session_duration_s += dt

            # Check if vehicle is full
            if self._connected_vehicle.soc >= self._connected_vehicle.params.soc_target:
                self._status = StationStatus.FINISHING

        elif self._status == StationStatus.FINISHING:
            self._current_power_kw = 0.0
            self._current_a = 0.0

        state = {
            "station_id": self.params.station_id,
            "name": self.params.name,
            "location": self.params.location,
            "status": self._status.value,
            "power_kw": round(self._current_power_kw, 4),
            "current_a": round(self._current_a, 3),
            "power_limit_kw": round(self._power_limit_kw, 3),
            "session_energy_kwh": round(self._session_energy_kwh, 4),
            "session_duration_min": round(self._session_duration_s / 60, 1),
            "total_energy_kwh": round(self._total_energy_kwh + self._session_energy_kwh, 3),
            "total_sessions": self._total_sessions,
            "revenue_eur": round(self._revenue_eur, 2),
            "cp_duty_cycle_pct": round(self._cp_duty_cycle * 100, 1),
            "connector_type": self.params.connector_type.value,
            "charging_mode": self.params.charging_mode.value,
            "vehicle_soc_pct": round(self._connected_vehicle.soc * 100, 1)
                                if self._connected_vehicle else None,
            "transaction_id": self._transaction_id,
        }
        self._history.append(state)
        return state

    @property
    def is_available(self) -> bool:
        return self._status == StationStatus.AVAILABLE

    @property
    def is_charging(self) -> bool:
        return self._status == StationStatus.CHARGING

    @property
    def power_kw(self) -> float:
        return self._current_power_kw

    @property
    def history(self) -> List[Dict]:
        return list(self._history)


class ChargingHub:
    """
    Multi-station charging hub — manages a fleet of charging stations.
    Provides aggregated power, load balancing interface.
    """

    def __init__(self, stations: List[ChargingStation]):
        self.stations = {s.params.station_id: s for s in stations}

    @property
    def total_power_kw(self) -> float:
        return sum(s.power_kw for s in self.stations.values())

    @property
    def n_charging(self) -> int:
        return sum(1 for s in self.stations.values() if s.is_charging)

    @property
    def n_available(self) -> int:
        return sum(1 for s in self.stations.values() if s.is_available)

    def get_station(self, station_id: str) -> Optional[ChargingStation]:
        return self.stations.get(station_id)

    def set_hub_power_limit(self, P_total_limit_kw: float, strategy: str = "equal"):
        """Distribute power limit across active stations."""
        active = [s for s in self.stations.values() if s.is_charging]
        if not active:
            return
        if strategy == "equal":
            P_each = P_total_limit_kw / len(active)
            for s in active:
                s.set_power_limit(P_each)
        elif strategy == "proportional":
            # Proportional to max capacity
            total_cap = sum(s.params.P_max_kw for s in active)
            for s in active:
                P_each = P_total_limit_kw * s.params.P_max_kw / max(total_cap, 1)
                s.set_power_limit(P_each)
        elif strategy == "priority":
            # Sorted by SoC (lowest SoC gets more power)
            sorted_stations = sorted(
                active,
                key=lambda s: s._connected_vehicle.soc if s._connected_vehicle else 1
            )
            remaining = P_total_limit_kw
            for i, s in enumerate(sorted_stations):
                P_each = min(s.params.P_max_kw, remaining / max(len(sorted_stations) - i, 1))
                s.set_power_limit(P_each)
                remaining -= P_each

    def step_all(self, dt: float = 1.0) -> List[Dict]:
        return [s.step(dt) for s in self.stations.values()]

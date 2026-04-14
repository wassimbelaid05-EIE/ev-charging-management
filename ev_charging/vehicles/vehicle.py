"""
Electric Vehicle Models
Battery model, charging behavior, arrival/departure simulation

Author: Wassim BELAID
"""

import numpy as np
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from datetime import datetime, timedelta
from enum import Enum
import random


class VehicleType(Enum):
    SEDAN       = "Sedan"
    SUV         = "SUV"
    VAN         = "Van"
    TRUCK       = "Light Truck"
    MOTORCYCLE  = "E-Motorcycle"
    BUS         = "E-Bus"


@dataclass
class VehicleParams:
    """EV battery and charging parameters."""
    vehicle_id: str
    name: str
    vehicle_type: VehicleType
    battery_capacity_kwh: float    # Usable capacity (kWh)
    max_ac_power_kw: float         # Max AC onboard charger (kW)
    max_dc_power_kw: float         # Max DC fast charge (kW)
    consumption_kwh_100km: float   # Energy consumption
    soc_target: float = 0.90       # Target SoC (90%)
    soc_min: float = 0.10          # Min SoC (protection)
    eta_charging: float = 0.94     # Battery charging efficiency
    # Arrival behavior
    arrival_soc_mean: float = 0.35  # Mean arrival SoC
    arrival_soc_std: float = 0.15   # Std of arrival SoC


# Fleet of EV models (realistic)
EV_FLEET = [
    VehicleParams("V001", "Tesla Model 3 LR",    VehicleType.SEDAN, 75, 11, 250, 14.5),
    VehicleParams("V002", "Renault Zoe",         VehicleType.SEDAN, 52, 22, 50,  17.2),
    VehicleParams("V003", "BMW iX3",             VehicleType.SUV,   74, 11, 150, 18.5),
    VehicleParams("V004", "VW ID.4",             VehicleType.SUV,   77, 11, 135, 19.0),
    VehicleParams("V005", "Nissan Leaf Plus",    VehicleType.SEDAN, 59, 22, 100, 16.0),
    VehicleParams("V006", "Peugeot e-208",       VehicleType.SEDAN, 46, 11, 100, 14.5),
    VehicleParams("V007", "Mercedes EQV",        VehicleType.VAN,   90, 22, 110, 28.0),
    VehicleParams("V008", "Tesla Model Y LR",    VehicleType.SUV,   75, 11, 250, 16.0),
    VehicleParams("V009", "Audi e-tron 50",      VehicleType.SUV,   64, 11, 150, 24.0),
    VehicleParams("V010", "Ford F-150 Lightning",VehicleType.TRUCK,131, 19, 150, 30.0),
]


class ElectricVehicle:
    """
    Electric Vehicle model with realistic battery behavior.

    Models:
    - CC-CV charging (Constant Current → Constant Voltage above 80% SoC)
    - SoC-dependent charging power curve
    - Battery thermal model (simplified)
    - Arrival/departure simulation
    - Energy consumption (kWh/100km)
    """

    def __init__(self, params: VehicleParams, initial_soc: Optional[float] = None):
        self.params = params
        if initial_soc is None:
            # Random arrival SoC from distribution
            soc = np.random.normal(params.arrival_soc_mean, params.arrival_soc_std)
            self._soc = float(np.clip(soc, params.soc_min, 0.8))
        else:
            self._soc = float(np.clip(initial_soc, 0, 1))

        self._energy_added_kwh = 0.0
        self._charging_time_min = 0.0
        self._arrival_time: Optional[datetime] = None
        self._departure_time: Optional[datetime] = None
        self._temperature_c = 25.0  # Battery temperature
        self._cycle_count = 0.0

    def get_charge_request_kw(self) -> float:
        """
        Vehicle requests power based on SoC and CC-CV algorithm.
        - Below 80% SoC: Constant Current (max power)
        - Above 80% SoC: Constant Voltage (tapered power)
        """
        if self._soc >= self.params.soc_target:
            return 0.0

        # Temperature derating (cold battery charges slower)
        temp_factor = np.clip(self._temperature_c / 25, 0.5, 1.0)

        if self._soc < 0.80:
            # CC phase: max power
            P_request = self.params.max_ac_power_kw * temp_factor
        else:
            # CV phase: taper from 100% to ~10% power
            taper = (1 - self._soc) / (1 - 0.80)
            P_request = self.params.max_ac_power_kw * taper * temp_factor

        return max(0.0, P_request)

    def charge(self, power_kw: float, dt_s: float):
        """Apply charging power to battery."""
        if self._soc >= self.params.soc_target:
            return

        energy_kwh = power_kw * self.params.eta_charging * dt_s / 3600
        d_soc = energy_kwh / self.params.battery_capacity_kwh
        self._soc = min(self.params.soc_target, self._soc + d_soc)
        self._energy_added_kwh += energy_kwh
        self._charging_time_min += dt_s / 60

        # Thermal model (simplified)
        P_heat = power_kw * (1 - self.params.eta_charging) * 0.5
        dT = P_heat / 50 * dt_s  # kJ/K thermal mass
        self._temperature_c = min(45, self._temperature_c + dT)

    @property
    def soc(self) -> float:
        return self._soc

    @property
    def soc_pct(self) -> float:
        return round(self._soc * 100, 1)

    @property
    def energy_needed_kwh(self) -> float:
        """Energy needed to reach target SoC."""
        return max(0, (self.params.soc_target - self._soc) * self.params.battery_capacity_kwh)

    @property
    def time_to_full_min(self) -> float:
        """Estimated time to reach target SoC (minutes)."""
        E_needed = self.energy_needed_kwh
        P_avg = self.params.max_ac_power_kw * 0.8  # Average accounting for CV taper
        if P_avg <= 0:
            return 0
        return E_needed / P_avg * 60

    def to_dict(self) -> dict:
        return {
            "vehicle_id": self.params.vehicle_id,
            "name": self.params.name,
            "type": self.params.vehicle_type.value,
            "soc_pct": self.soc_pct,
            "battery_kwh": self.params.battery_capacity_kwh,
            "energy_added_kwh": round(self._energy_added_kwh, 3),
            "charging_time_min": round(self._charging_time_min, 1),
            "energy_needed_kwh": round(self.energy_needed_kwh, 2),
            "time_to_full_min": round(self.time_to_full_min, 0),
            "temperature_c": round(self._temperature_c, 1),
            "max_ac_kw": self.params.max_ac_power_kw,
        }


class EVFleetSimulator:
    """
    Simulates EV arrival/departure patterns for a commercial location.
    Based on probabilistic models (Gaussian mixture for arrival times).
    """

    # Arrival patterns by location type
    ARRIVAL_PATTERNS = {
        "office": [
            (8.0, 1.0, 0.45),   # Morning peak (hour_mean, hour_std, fraction)
            (12.0, 0.5, 0.15),  # Lunch
            (18.0, 1.0, 0.40),  # Evening
        ],
        "shopping": [
            (10.0, 1.5, 0.30),
            (14.0, 1.0, 0.40),
            (17.0, 1.0, 0.30),
        ],
        "highway": [
            (7.0, 2.0, 0.25),
            (12.0, 1.0, 0.20),
            (17.0, 2.0, 0.30),
            (21.0, 1.5, 0.25),
        ],
        "residential": [
            (17.5, 1.5, 0.60),
            (22.0, 1.0, 0.40),
        ],
    }

    STAY_DURATION = {
        "office": (480, 60),        # 8h ± 1h (min)
        "shopping": (60, 30),
        "highway": (25, 10),
        "residential": (600, 120),
    }

    def __init__(self, location_type: str = "office", n_stations: int = 10):
        self.location_type = location_type
        self.n_stations = n_stations
        self._scheduled_arrivals: List[Dict] = []
        self._active_vehicles: Dict[str, ElectricVehicle] = {}

    def generate_daily_schedule(self, date: datetime, n_vehicles: int = 20) -> List[Dict]:
        """Generate arrival/departure schedule for one day."""
        patterns = self.ARRIVAL_PATTERNS.get(self.location_type, self.ARRIVAL_PATTERNS["office"])
        stay_mean, stay_std = self.STAY_DURATION.get(self.location_type, (60, 30))

        schedule = []
        for i in range(n_vehicles):
            # Select arrival pattern
            fractions = [p[2] for p in patterns]
            pattern = random.choices(patterns, weights=fractions)[0]
            hour_mean, hour_std, _ = pattern

            # Arrival time
            arrival_h = np.random.normal(hour_mean, hour_std)
            arrival_h = max(0, min(23.5, arrival_h))
            arrival_dt = date.replace(hour=0, minute=0, second=0) + timedelta(hours=arrival_h)

            # Stay duration
            stay_min = max(15, np.random.normal(stay_mean, stay_std))
            departure_dt = arrival_dt + timedelta(minutes=stay_min)

            # Vehicle
            vehicle_params = random.choice(EV_FLEET)
            soc_arrival = float(np.clip(
                np.random.normal(vehicle_params.arrival_soc_mean, vehicle_params.arrival_soc_std),
                0.10, 0.80
            ))

            schedule.append({
                "vehicle_id": f"V{i+1:03d}",
                "vehicle_name": vehicle_params.name,
                "vehicle_type": vehicle_params.vehicle_type.value,
                "arrival_time": arrival_dt,
                "departure_time": departure_dt,
                "stay_min": round(stay_min, 0),
                "arrival_soc_pct": round(soc_arrival * 100, 1),
                "battery_kwh": vehicle_params.battery_capacity_kwh,
                "max_power_kw": vehicle_params.max_ac_power_kw,
                "params": vehicle_params,
            })

        schedule.sort(key=lambda x: x["arrival_time"])
        self._scheduled_arrivals = schedule
        return schedule

    def get_active_at(self, current_time: datetime) -> List[Dict]:
        """Get vehicles present at given time."""
        return [s for s in self._scheduled_arrivals
                if s["arrival_time"] <= current_time <= s["departure_time"]]

    def get_arrivals_at(self, current_time: datetime, window_s: float = 60) -> List[Dict]:
        """Get vehicles arriving in the next window_s seconds."""
        t_end = current_time + timedelta(seconds=window_s)
        return [s for s in self._scheduled_arrivals
                if current_time <= s["arrival_time"] < t_end]

    def get_departures_at(self, current_time: datetime, window_s: float = 60) -> List[Dict]:
        """Get vehicles departing in the next window_s seconds."""
        t_end = current_time + timedelta(seconds=window_s)
        return [s for s in self._scheduled_arrivals
                if current_time <= s["departure_time"] < t_end]

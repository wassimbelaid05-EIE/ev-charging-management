"""
Dynamic Tariff & Grid Integration
Time-of-Use pricing, spot market, demand charge management

Standards: EN 62196, IEC 62196-3, Smart Meter regulations
Author: Wassim BELAID
"""

import numpy as np
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
from enum import Enum
from collections import deque


class TariffType(Enum):
    FIXED        = "fixed"           # Simple flat rate
    TOU          = "time_of_use"     # Time-of-Use (peak/off-peak)
    SPOT         = "spot_market"     # Real-time spot price
    DYNAMIC      = "dynamic"         # Fully dynamic (15-min intervals)
    RTP          = "real_time_pricing"


@dataclass
class TariffParams:
    """Electricity tariff configuration."""
    name: str = "Swiss TOU Tariff"
    tariff_type: TariffType = TariffType.TOU
    currency: str = "CHF"

    # Fixed tariff
    base_rate_eur_kwh: float = 0.28

    # TOU tariff (Swiss typical)
    peak_rate_eur_kwh: float = 0.38      # 07:00 - 22:00
    offpeak_rate_eur_kwh: float = 0.22   # 22:00 - 07:00
    weekend_rate_eur_kwh: float = 0.24

    # Peak hours definition
    peak_start_h: float = 7.0
    peak_end_h: float = 22.0

    # Demand charge (€/kW for peak demand)
    demand_charge_eur_kw: float = 8.50   # Monthly peak demand charge
    demand_measurement_window_min: int = 15  # 15-min peak

    # Grid connection limit
    grid_connection_kw: float = 150.0    # Max grid power (subscription)
    grid_connection_cost_eur_mo: float = 180.0  # Monthly subscription

    # Carbon intensity (gCO₂/kWh)
    carbon_intensity_gco2_kwh: float = 45.0  # Swiss average (very low, hydro)

    # Feed-in tariff (for V2G)
    feedin_rate_eur_kwh: float = 0.08

    # Taxes and levies
    vat_pct: float = 7.7          # Swiss VAT
    network_charge_eur_kwh: float = 0.08  # Grid usage charge
    levies_eur_kwh: float = 0.02   # Renewable energy levies


class DynamicTariff:
    """
    Dynamic electricity tariff model.

    Implements:
    - Time-of-Use (TOU) pricing
    - Day-ahead spot market prices (EPEX-style simulation)
    - Real-time price signals
    - Demand charge tracking (15-min peak)
    - Carbon intensity tracking
    - Price forecasting for optimization

    Usage:
        tariff = DynamicTariff(TariffParams())
        price = tariff.get_price(datetime.now())
        forecast = tariff.get_24h_forecast(datetime.now())
    """

    def __init__(self, params: TariffParams = None):
        self.params = params or TariffParams()
        self._spot_prices: Dict[str, float] = {}  # {datetime_key: price}
        self._generate_spot_prices()
        self._peak_demand_tracker: deque = deque(maxlen=96)  # 24h × 4 (15-min)
        self._demand_window_kw: deque = deque(maxlen=4)  # 1-hour window of 15-min peaks
        self._monthly_peak_kw = 0.0
        self._monthly_cost_eur = 0.0
        self._t = 0.0

    def _generate_spot_prices(self):
        """Generate realistic EPEX spot prices for 24h."""
        # Base price pattern (low night, high morning/evening)
        hours = np.arange(0, 24, 0.25)
        base = 45  # €/MWh average

        # Price shape: low at night (2-6h), two peaks (8-10h, 17-20h)
        shape = (
            base +
            30 * np.exp(-((hours - 3) ** 2) / 4) * (-1) +   # Night valley
            25 * np.exp(-((hours - 9) ** 2) / 2) +           # Morning peak
            35 * np.exp(-((hours - 18.5) ** 2) / 3) +        # Evening peak
            10 * np.random.normal(0, 1, len(hours))           # Noise
        )
        shape = np.maximum(20, shape)  # Floor at 20 €/MWh

        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        for i, h in enumerate(hours):
            t = today + timedelta(hours=float(h))
            key = t.strftime("%Y%m%d%H%M")
            self._spot_prices[key] = round(float(shape[i]) / 1000, 4)  # €/kWh

    def get_price(self, dt: datetime, include_taxes: bool = True) -> float:
        """
        Get electricity price at given datetime (€/kWh).
        """
        p = self.params

        if p.tariff_type == TariffType.FIXED:
            base = p.base_rate_eur_kwh

        elif p.tariff_type == TariffType.TOU:
            hour = dt.hour + dt.minute / 60
            is_weekend = dt.weekday() >= 5
            if is_weekend:
                base = p.weekend_rate_eur_kwh
            elif p.peak_start_h <= hour < p.peak_end_h:
                base = p.peak_rate_eur_kwh
            else:
                base = p.offpeak_rate_eur_kwh

        elif p.tariff_type in (TariffType.SPOT, TariffType.DYNAMIC):
            # Find nearest 15-min slot
            t_rounded = dt.replace(second=0, microsecond=0)
            t_rounded = t_rounded.replace(minute=(dt.minute // 15) * 15)
            key = t_rounded.strftime("%Y%m%d%H%M")
            base = self._spot_prices.get(key, p.base_rate_eur_kwh)

        else:
            base = p.base_rate_eur_kwh

        if include_taxes:
            total = (base + p.network_charge_eur_kwh + p.levies_eur_kwh) * (1 + p.vat_pct / 100)
        else:
            total = base

        return round(total, 5)

    def get_carbon_intensity(self, dt: datetime) -> float:
        """Carbon intensity (gCO₂/kWh) — varies with grid mix."""
        hour = dt.hour
        # Higher at peak (more fossil backup), lower at midday (solar)
        variation = 1.0 + 0.3 * np.sin((hour - 6) * np.pi / 12)
        return round(self.params.carbon_intensity_gco2_kwh * variation, 1)

    def update_demand(self, power_kw: float, dt_s: float) -> Dict:
        """
        Track demand for demand charge calculation.
        Returns current demand charge estimate.
        """
        self._demand_window_kw.append(power_kw)
        avg_15min = np.mean(self._demand_window_kw) if self._demand_window_kw else 0

        if len(self._demand_window_kw) >= 4:
            self._peak_demand_tracker.append(avg_15min)
            self._monthly_peak_kw = max(self._monthly_peak_kw, avg_15min)

        demand_charge = self._monthly_peak_kw * self.params.demand_charge_eur_kw

        return {
            "current_power_kw": round(power_kw, 3),
            "avg_15min_kw": round(avg_15min, 3),
            "monthly_peak_kw": round(self._monthly_peak_kw, 3),
            "demand_charge_eur": round(demand_charge, 2),
        }

    def get_24h_forecast(self, start_dt: datetime,
                          n_points: int = 96) -> List[Dict]:
        """Get 24h price forecast (15-min intervals)."""
        forecast = []
        dt_h = 24 / n_points

        for i in range(n_points):
            t = start_dt + timedelta(hours=i * dt_h)
            price = self.get_price(t)
            carbon = self.get_carbon_intensity(t)

            # Price signal: 1=cheap, 0=expensive
            tou_raw = self.get_price(t, include_taxes=False)
            p = self.params
            price_range = p.peak_rate_eur_kwh - p.offpeak_rate_eur_kwh
            signal = 1 - (tou_raw - p.offpeak_rate_eur_kwh) / max(price_range, 0.01)
            signal = float(np.clip(signal, 0, 1))

            forecast.append({
                "timestamp": t.isoformat(),
                "hour": t.hour + t.minute / 60,
                "price_eur_kwh": price,
                "price_excl_tax": tou_raw,
                "carbon_gco2_kwh": carbon,
                "charge_signal": round(signal, 3),  # 1=charge now, 0=avoid
                "is_peak": p.peak_start_h <= (t.hour + t.minute / 60) < p.peak_end_h,
            })

        return forecast

    def compute_charging_cost(self, energy_kwh: float, dt: datetime) -> Dict:
        """Compute cost for a charging session."""
        price = self.get_price(dt)
        total_eur = energy_kwh * price
        vat = total_eur * self.params.vat_pct / 100
        carbon = energy_kwh * self.get_carbon_intensity(dt) / 1000  # kg CO₂

        return {
            "energy_kwh": round(energy_kwh, 3),
            "price_eur_kwh": round(price, 4),
            "total_eur": round(total_eur, 2),
            "vat_eur": round(vat, 2),
            "carbon_kg": round(carbon, 3),
        }

    def optimal_charge_window(self, energy_needed_kwh: float,
                               max_duration_h: float,
                               forecast: List[Dict]) -> List[int]:
        """
        Find cheapest time slots to charge.
        Returns indices of cheapest slots to use.
        """
        if not forecast:
            return []

        prices = [(i, f["price_eur_kwh"]) for i, f in enumerate(forecast)]
        prices.sort(key=lambda x: x[1])

        # Select enough cheap slots
        dt_h = 24 / len(forecast)
        slots_needed = int(np.ceil(energy_needed_kwh / (22.0 * dt_h)))  # 22kW max
        slots_needed = min(slots_needed, int(max_duration_h / dt_h))

        selected = sorted([p[0] for p in prices[:slots_needed]])
        return selected

    @property
    def monthly_peak_kw(self) -> float:
        return self._monthly_peak_kw

    @property
    def estimated_monthly_demand_charge(self) -> float:
        return round(self._monthly_peak_kw * self.params.demand_charge_eur_kw, 2)

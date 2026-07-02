"""
solar.py — model a day of hourly PV generation with pvlib.

For the MVP we use pvlib's clear-sky model (Ineichen) at the user's location,
scaled by system size and a simple weather/cloud factor. This needs no external
data download, so the app runs instantly and offline. In v2 this is where PVGIS
or NASA POWER real irradiance would slot in (same output shape).

Output: an hourly Series of AC power in kW for the given day.
"""

from __future__ import annotations
import datetime as dt
import numpy as np
import pandas as pd
import pvlib


# A few preset locations so users don't need coordinates handy.
LOCATIONS = {
    "Berlin":     (52.52, 13.405, "Europe/Berlin"),
    "Munich":     (48.137, 11.575, "Europe/Berlin"),
    "Hamburg":    (53.551, 9.993, "Europe/Berlin"),
    "Cologne":    (50.937, 6.960, "Europe/Berlin"),
    "Frankfurt":  (50.110, 8.682, "Europe/Berlin"),
    "Hannover":   (52.376, 9.732, "Europe/Berlin"),
}


def pv_generation(day: dt.date, lat: float, lon: float, tz: str,
                  kwp: float, tilt: float = 30, azimuth: float = 180,
                  weather_factor: float = 0.85) -> pd.Series:
    """Hourly AC power (kW) for a PV array on the given day.

    kwp: system size in kWp (kilowatt-peak).
    tilt: panel tilt in degrees (0 = flat, 90 = vertical).
    azimuth: 180 = south (northern hemisphere optimum).
    weather_factor: 0..1 crude derate for clouds + system losses.
    """
    loc = pvlib.location.Location(lat, lon, tz=tz)
    times = pd.date_range(
        dt.datetime.combine(day, dt.time(0, 0)),
        periods=24, freq="1h", tz=tz)

    solpos = loc.get_solarposition(times)
    clearsky = loc.get_clearsky(times, model="ineichen")  # ghi, dni, dhi

    # Plane-of-array irradiance for the tilted panel.
    poa = pvlib.irradiance.get_total_irradiance(
        surface_tilt=tilt,
        surface_azimuth=azimuth,
        solar_zenith=solpos["apparent_zenith"],
        solar_azimuth=solpos["azimuth"],
        dni=clearsky["dni"],
        ghi=clearsky["ghi"],
        dhi=clearsky["dhi"],
    )
    poa_global = poa["poa_global"].fillna(0.0)

    # Simple PV model: power scales with POA vs standard test 1000 W/m^2,
    # times system size, times a weather/loss derate.
    ac_kw = (poa_global / 1000.0) * kwp * weather_factor
    ac_kw = ac_kw.clip(lower=0)
    ac_kw.index = ac_kw.index.tz_localize(None)   # naive index for merging
    ac_kw.name = "pv_kw"
    return ac_kw.round(3)


def daily_load_profile(day: dt.date, daily_kwh: float = 9.0) -> pd.Series:
    """A typical residential load shape (kW), scaled to daily_kwh per day.

    Two humps: a morning rise and a stronger evening peak, low overnight.
    """
    times = pd.date_range(
        dt.datetime.combine(day, dt.time(0, 0)), periods=24, freq="1h")
    h = np.arange(24)
    shape = (
        0.4
        + 0.7 * np.exp(-((h - 7.5) ** 2) / 4)    # morning
        + 1.2 * np.exp(-((h - 19.5) ** 2) / 6)   # evening peak
    )
    shape = shape / shape.sum()                  # normalise to fractions
    load_kw = shape * daily_kwh                  # kWh across the day == daily_kwh
    s = pd.Series(np.round(load_kw, 3), index=times, name="load_kw")
    return s


if __name__ == "__main__":
    day = dt.date.today()
    pv = pv_generation(day, 52.52, 13.405, "Europe/Berlin", kwp=8.0)
    load = daily_load_profile(day, 9.0)
    print("PV daily kWh:", round(pv.sum(), 2))
    print("Peak PV kW:", round(pv.max(), 2), "at", pv.idxmax().hour, "h")
    print("Load daily kWh:", round(load.sum(), 2))
    print(pv.round(2).to_string())

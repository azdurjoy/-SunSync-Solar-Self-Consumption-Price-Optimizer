"""
prices.py — German day-ahead electricity prices.

Primary source: aWATTar API (Germany), which needs no API key.
    https://api.awattar.de/v1/marketdata
If the network is unavailable (offline demo, restricted sandbox), we fall back
to a realistic synthetic day so the app always runs. The fallback is clearly
flagged in the UI so nobody mistakes it for live data.

Prices are handled internally in EUR/kWh (aWATTar returns EUR/MWh).
"""

from __future__ import annotations
import datetime as dt
import requests
import pandas as pd
import numpy as np

AWATTAR_DE = "https://api.awattar.de/v1/marketdata"


def fetch_awattar(day: dt.date | None = None, timeout: int = 20):
    """Return an hourly price series (EUR/kWh) for the given day.

    Returns (series, is_live). If the request fails, is_live is False and a
    synthetic day is returned instead.
    """
    day = day or dt.date.today()
    start = dt.datetime.combine(day, dt.time(0, 0))
    end = start + dt.timedelta(days=1)
    params = {
        "start": int(start.timestamp() * 1000),
        "end": int(end.timestamp() * 1000),
    }
    try:
        r = requests.get(AWATTAR_DE, params=params,
                         headers={"User-Agent": "SunSync/1.0"}, timeout=timeout)
        r.raise_for_status()
        data = r.json()["data"]
        if not data:
            raise ValueError("empty price data")
        idx, vals = [], []
        for row in data:
            ts = dt.datetime.fromtimestamp(row["start_timestamp"] / 1000)
            idx.append(pd.Timestamp(ts))
            vals.append(row["marketprice"] / 1000.0)   # EUR/MWh -> EUR/kWh
        s = pd.Series(vals, index=pd.DatetimeIndex(idx), name="price_eur_kwh")
        s = s.resample("1h").ffill().iloc[:24]
        return s, True
    except Exception:
        return sample_prices(day), False


def sample_prices(day: dt.date | None = None):
    """A realistic synthetic German day-ahead curve (EUR/kWh).

    Captures the shape that matters for this app: a midday dip (solar glut,
    sometimes negative) and morning/evening peaks.
    """
    day = day or dt.date.today()
    start = pd.Timestamp(dt.datetime.combine(day, dt.time(0, 0)))
    hours = pd.date_range(start, periods=24, freq="1h")
    h = np.arange(24)
    # base level ~0.09, morning peak ~7-9h, evening peak ~18-20h, midday dip 11-15h
    curve = (
        0.09
        + 0.05 * np.exp(-((h - 8) ** 2) / 6)     # morning peak
        + 0.08 * np.exp(-((h - 19) ** 2) / 5)    # evening peak
        - 0.11 * np.exp(-((h - 13) ** 2) / 4)    # midday solar dip
    )
    # push midday clearly negative on the sunniest hours to show the feature
    curve[12:14] -= 0.03
    s = pd.Series(np.round(curve, 4), index=hours, name="price_eur_kwh")
    return s


if __name__ == "__main__":
    s, live = fetch_awattar()
    print("live:", live)
    print(s.round(3).to_string())
    print("min", round(s.min(), 3), "max", round(s.max(), 3), "EUR/kWh")
    print("negative hours:", list(s[s < 0].index.hour))

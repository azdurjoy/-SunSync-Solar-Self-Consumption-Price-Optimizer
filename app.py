"""
SunSync — Solar Self-Consumption & Price Optimizer (Streamlit v1)

Run locally:
    pip install -r requirements.txt
    streamlit run app.py

What it does: models a day of rooftop-solar generation (pvlib), pulls German
day-ahead electricity prices (aWATTar), and simulates how a home battery should
use, store, or export power — including avoiding export into negative-price
hours. Compares a naive baseline against a price-aware strategy and shows the
self-consumption gain and money difference, plus plain-language tips.
"""

import datetime as dt
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

from prices import fetch_awattar
from solar import pv_generation, daily_load_profile, LOCATIONS
from simulate import simulate, recommendations

st.set_page_config(page_title="SunSync — Solar Optimizer",
                   page_icon="☀️", layout="wide")

# ---- header ----
st.title("☀️ SunSync")
st.markdown("**Solar self-consumption & price optimizer for German homes** — "
            "when should you *use, store, or export* your solar power?")

# ---- sidebar: system setup ----
with st.sidebar:
    st.header("Your system")
    city = st.selectbox("Location", list(LOCATIONS.keys()), index=0)
    lat, lon, tz = LOCATIONS[city]

    kwp = st.slider("Solar array size (kWp)", 1.0, 20.0, 8.0, 0.5)
    weather = st.slider("Sky condition today", 0.1, 1.0, 0.85, 0.05,
                        help="1.0 = clear sky, lower = cloudier. A simple derate "
                             "standing in for real weather data (added in v2).")
    tilt = st.slider("Panel tilt (°)", 0, 60, 30)
    azimuth = st.slider("Panel direction (° from north)", 90, 270, 180,
                        help="180° = south (optimal in the northern hemisphere).")

    st.header("Battery")
    battery_kwh = st.slider("Battery capacity (kWh)", 0.0, 30.0, 10.0, 0.5)
    battery_kw = st.slider("Max charge/discharge (kW)", 1.0, 15.0, 5.0, 0.5)

    st.header("Consumption")
    daily_kwh = st.slider("Daily household use (kWh)", 3.0, 40.0, 12.0, 0.5)

    st.header("Tariff & strategy")
    grid_adder = st.slider("Grid fees + levies on imports (€/kWh)",
                           0.0, 0.30, 0.15, 0.01,
                           help="Fixed retail markup added to the spot price "
                                "when you buy from the grid.")
    enable_arbitrage = st.checkbox(
        "Try grid arbitrage (charge from cheap grid)", value=False,
        help="Charge the battery from cheap/negative-price grid power to cover "
             "the evening peak. Often marginal for home batteries after "
             "round-trip losses — toggle to see the effect.")

    day = st.date_input("Day", dt.date.today())

# ---- data ----
price, is_live = fetch_awattar(day)
# align price index to the model day
pv = pv_generation(day, lat, lon, tz, kwp=kwp, tilt=tilt,
                   azimuth=azimuth, weather_factor=weather)
load = daily_load_profile(day, daily_kwh)
# make the three series share one clean hourly index
price.index = pv.index

if is_live:
    st.success(f"Live day-ahead prices from aWATTar for {day:%d %b %Y}.")
else:
    st.info("⚠️ Using a realistic **sample** price curve (live aWATTar feed not "
            "reachable right now). Numbers are illustrative.")

# ---- simulate both strategies ----
led_naive, sum_naive = simulate(pv, load, price, battery_kwh=battery_kwh,
                                battery_kw=battery_kw, grid_adder=grid_adder,
                                strategy="naive")
led_opt, sum_opt = simulate(pv, load, price, battery_kwh=battery_kwh,
                            battery_kw=battery_kw, grid_adder=grid_adder,
                            strategy="optimized", enable_arbitrage=enable_arbitrage)

daily_saving = round(sum_naive["total_cost_eur"] - sum_opt["total_cost_eur"], 2)

# ---- headline metrics ----
c1, c2, c3, c4 = st.columns(4)
c1.metric("PV generated today", f"{sum_opt['pv_total_kwh']:.1f} kWh")
c2.metric("Self-consumption",
          f"{sum_opt['self_consumption_pct']:.0f}%",
          f"{sum_opt['self_consumption_pct'] - sum_naive['self_consumption_pct']:+.0f}% vs naive")
c3.metric("Day cost (optimized)", f"€{sum_opt['total_cost_eur']:.2f}",
          f"€{-daily_saving:+.2f} vs naive", delta_color="inverse")
c4.metric("Est. yearly difference", f"€{daily_saving*365:,.0f}",
          help="Daily saving × 365 — a rough indicative annualisation.")

# ---- the day chart ----
st.subheader(f"{city} · {day:%A %d %B %Y}")

fig = make_subplots(specs=[[{"secondary_y": True}]])
hours = [f"{h:02d}" for h in led_opt["hour"]]

fig.add_trace(go.Bar(x=hours, y=led_opt["pv_kw"], name="Solar (kW)",
                     marker_color="#F4A63A", opacity=0.85), secondary_y=False)
fig.add_trace(go.Scatter(x=hours, y=led_opt["load_kw"], name="Household load (kW)",
                         mode="lines+markers", line=dict(color="#3A6EA5", width=2)),
              secondary_y=False)
fig.add_trace(go.Scatter(x=hours, y=led_opt["soc_kwh"], name="Battery (kWh)",
                         mode="lines", line=dict(color="#2E9E6B", width=2, dash="dot")),
              secondary_y=False)
fig.add_trace(go.Scatter(x=hours, y=led_opt["price"], name="Price (€/kWh)",
                         mode="lines", line=dict(color="#B23A48", width=2)),
              secondary_y=True)
# shade negative-price hours
neg = led_opt[led_opt["price"] < 0]
for h in neg["hour"]:
    fig.add_vrect(x0=f"{h:02d}", x1=f"{h:02d}", fillcolor="#B23A48",
                  opacity=0.10, line_width=8)

fig.update_layout(height=440, barmode="overlay",
                  legend=dict(orientation="h", y=1.12),
                  margin=dict(t=30, b=10, l=10, r=10),
                  plot_bgcolor="white")
fig.update_yaxes(title_text="Power (kW) / Battery (kWh)", secondary_y=False)
fig.update_yaxes(title_text="Price (€/kWh)", secondary_y=True, zeroline=True,
                 zerolinecolor="#B23A48")
fig.update_xaxes(title_text="Hour of day")
st.plotly_chart(fig, use_container_width=True)

if (led_opt["price"] < 0).any():
    st.caption("🔴 Shaded hours have **negative** wholesale prices — exporting then "
               "earns nothing, so the optimizer self-consumes or holds instead.")

# ---- recommendations ----
st.subheader("Today's recommendations")
for tip in recommendations(pv, load, price, battery_kwh=battery_kwh):
    st.markdown(f"- {tip}")

# ---- detail + comparison ----
with st.expander("Naive vs. optimized — the numbers"):
    comp = pd.DataFrame({
        "Naive (use-as-it-comes)": [
            f"€{sum_naive['total_cost_eur']:.2f}",
            f"{sum_naive['self_consumption_pct']:.0f}%",
            f"{sum_naive['grid_import_kwh']:.1f} kWh",
            f"{sum_naive['grid_export_kwh']:.1f} kWh",
        ],
        "Optimized (price-aware)": [
            f"€{sum_opt['total_cost_eur']:.2f}",
            f"{sum_opt['self_consumption_pct']:.0f}%",
            f"{sum_opt['grid_import_kwh']:.1f} kWh",
            f"{sum_opt['grid_export_kwh']:.1f} kWh",
        ],
    }, index=["Day cost", "Self-consumption", "Grid import", "Grid export"])
    st.table(comp)
    st.caption("Self-consumption is the share of your solar you use yourself "
               "(directly or via the battery) rather than exporting. Higher is "
               "usually better — you avoid buying that energy back later at a "
               "higher retail price.")

with st.expander("Hourly ledger (optimized)"):
    st.dataframe(led_opt, use_container_width=True)

st.caption("SunSync v1 · PV modelled with pvlib (clear-sky) · prices from "
           "aWATTar · a simplified hourly model for illustration, not financial "
           "advice.")

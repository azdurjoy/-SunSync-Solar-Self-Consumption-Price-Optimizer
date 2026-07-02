
# ☀️ SunSync — Solar Self-Consumption & Price Optimizer

**When should a German home use, store, or export its solar power?**
SunSync models a day of rooftop-solar generation, pulls live German day-ahead
electricity prices, and simulates how a home battery should behave — including
**avoiding export into negative-price hours** — then shows the self-consumption
gain and money difference versus a naive setup.

Built with Python · pvlib · Streamlit · Plotly.

<img width="1440" height="765" alt="Screenshot 2026-07-02 at 2 32 09 PM" src="https://github.com/user-attachments/assets/2716ba76-1212-46ba-9bf9-4866f17c9362" />
<img width="1440" height="765" alt="Screenshot 2026-07-02 at 2 33 11 PM" src="https://github.com/user-attachments/assets/4b0a54ef-8830-4183-89c9-92dd6fc01a6c" />

-->

---

## Why this exists

Germany has a growing problem at the household level:

- Since 2026, **feed-in remuneration is suspended during negative-price
  periods** — exactly the sunny midday hours when everyone's panels export and
  wholesale prices crash below zero. Exporting then earns nothing.
- Yet only about **3% of connection points have a smart meter** (vs. an EU
  average above 60%), so households have almost no visibility into *when* their
  solar power is actually valuable to use, store, or export.

The result: homeowners with PV and a battery fly blind — dumping cheap power at
noon and buying expensive power at 7 pm, when a smarter schedule would store the
midday surplus and self-consume it during the evening peak.

SunSync makes that decision visible.

---

## What it does

- **Models PV generation** for your location, array size, tilt, and azimuth
  using [`pvlib`](https://pvlib-python.readthedocs.io/) (clear-sky model).
- **Pulls German day-ahead prices** from the [aWATTar API](https://www.awattar.de/)
  (no API key), with a realistic sample-day fallback when offline.
- **Simulates a home battery** hour by hour under two strategies:
  - **Naive** — use solar as it comes, export the rest regardless of price
    (how most systems run today).
  - **Optimized** — price-aware: never export into negative prices, and reserve
    stored solar for the expensive evening peak. Optional grid-arbitrage toggle.
- **Shows the difference** — self-consumption %, daily cost, indicative yearly
  difference, an interactive day chart (solar, load, battery, price), and
  plain-language recommendations.

---

## Quick start

```bash
pip install -r requirements.txt
streamlit run app.py
```

Then open the local URL Streamlit prints (usually `http://localhost:8501`).

---

## Project structure

| File | Purpose |
|------|---------|
| `app.py` | Streamlit UI + day chart |
| `solar.py` | PV generation model (pvlib) + load profile |
| `prices.py` | aWATTar price fetch + offline fallback |
| `simulate.py` | Battery dispatch simulation + recommendations |
| `requirements.txt` | Dependencies |

---

## How the model works (methodology)

Prices are handled in €/kWh; imports are billed at the spot price plus a fixed
grid/levy adder, while exports earn the spot price **only when positive**
(mirroring the 2026 rule that removes remuneration during negative prices).

The battery is simulated at hourly resolution with a round-trip efficiency. The
**optimized** strategy:
1. serves load directly from solar first,
2. charges the battery from surplus solar,
3. exports remaining surplus only when the price is positive (otherwise holds /
   curtails rather than paying to export),
4. reserves battery charge to cover the evening peak instead of draining it
   early.

An **honest finding** the tool surfaces: after round-trip losses and the fixed
grid adder, pure grid *arbitrage* (buying cheap grid power to resell/use at the
peak) is usually marginal for home batteries — so it's off by default and
provided as a toggle. The optimizer's reliable win is **higher
self-consumption** and **never dumping energy into negative-price hours**.

---

## Roadmap

- **v2** — real irradiance from PVGIS / NASA POWER (replaces clear-sky derate);
  tomorrow's prices; EV and heat-pump as shiftable loads; save/compare systems.
- **v3** — replace the rule-based dispatch with a **linear-program optimizer**
  (PuLP/scipy) for provably optimal scheduling; ENTSO-E data depth; downloadable
  PDF/Excel day report.
- Deploy a live demo on Streamlit Community Cloud.

---

## Data sources (all free)

- **aWATTar** — German day-ahead prices, no key.
- **Energy-Charts (Fraunhofer ISE)** / **SMARD.de (Bundesnetzagentur)** —
  alternative free price/generation feeds (planned).
- **ENTSO-E Transparency Platform** — full EU market data (free key).
- **pvlib** + **PVGIS / NASA POWER** — solar modelling.

---

## Disclaimer

A simplified hourly model for **illustration and education**, not financial
advice. Real savings depend on your tariff, metering, weather, and battery
hardware. Verify figures before making purchase decisions.

## License


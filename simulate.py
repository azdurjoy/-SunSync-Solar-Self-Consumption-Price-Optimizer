"""
simulate.py — hour-by-hour energy + money simulation.

Two strategies over one day, on the same PV / load / price inputs:

  NAIVE      — the "dumb" default most homes run today: use solar as it comes,
               charge the battery only from leftover surplus, export the rest
               regardless of price (even when price is zero or negative).

  OPTIMIZED  — price-aware: it avoids exporting into negative/near-zero prices
               (self-consuming or holding instead) and preserves stored energy
               to cover the expensive evening peak, and flags cheap/free hours
               as good times to run shiftable loads.

Both return an hourly ledger and a cost total. The difference is the headline
number: "you'd save €X and waste Y kWh less by scheduling smartly."

Simplifying MVP assumptions (documented so they're honest):
  - Hourly resolution, one battery, round-trip efficiency applied on charge.
  - Import is billed at the day-ahead price plus a fixed grid/levy adder.
  - Export earns the day-ahead price, but only when positive (mirrors the 2026
    rule that removes remuneration during negative prices).
"""

from __future__ import annotations
import pandas as pd
import numpy as np


def simulate(pv_kw, load_kw, price_eur_kwh,
             battery_kwh: float = 10.0,
             battery_kw: float = 5.0,
             rte: float = 0.90,
             grid_adder: float = 0.15,
             strategy: str = "optimized",
             enable_arbitrage: bool = False,
             negative_price_threshold: float = 0.0):
    """Run one day. Returns (ledger_df, summary_dict).

    grid_adder: fixed EUR/kWh added to the spot price for imports (grid fees,
        levies, supplier margin) — a realistic retail markup.
    enable_arbitrage: if True, the optimized strategy may charge the battery
        from cheap grid power to cover the evening peak. Off by default because,
        after round-trip losses and the fixed grid adder, home-battery grid
        arbitrage is usually marginal — a finding the app makes visible.
    """
    idx = pv_kw.index
    n = len(idx)
    soc = 0.0                      # state of charge (kWh), start empty
    max_charge = battery_kw
    max_discharge = battery_kw

    # --- Pre-compute plan for the optimized strategy ---------------------
    # Evening peak = the priciest block; estimate the grid energy we'll want
    # stored to cover it, then pick the cheapest pre-peak hours to buy that
    # energy (only if the spread beats round-trip + adder cost).
    hours = idx.hour
    evening_mask = (hours >= 17) & (hours <= 23)
    evening_deficit = float((load_kw[evening_mask] - pv_kw[evening_mask]).clip(lower=0).sum())
    peak_price = float(price_eur_kwh[evening_mask].max()) if evening_mask.any() else float(price_eur_kwh.max())

    arb_hours = set()
    if enable_arbitrage and evening_deficit > 0:
        pre_peak = price_eur_kwh[hours < 17].sort_values()
        need = min(evening_deficit, battery_kwh)   # can't store more than capacity
        acc = 0.0
        for ts, p in pre_peak.items():
            charge_cost = (p + grid_adder) / rte
            if (peak_price + grid_adder) > charge_cost + 0.03 and acc < need:
                arb_hours.add(ts)
                acc += max_charge
            if acc >= need:
                break

    rows = []
    for i in range(n):
        pv = float(pv_kw.iloc[i])
        load = float(load_kw.iloc[i])
        price = float(price_eur_kwh.iloc[i])
        import_price = price + grid_adder
        export_price = max(price, 0.0)   # no pay for negative-price export

        # 1) solar serves load first
        direct = min(pv, load)
        surplus = pv - direct           # >=0 solar left after load
        deficit = load - direct         # >=0 load not yet covered

        charge = discharge = grid_import = grid_export = 0.0

        if strategy == "naive":
            # Charge from surplus, export the rest no matter the price (even
            # negative). Discharge to cover any deficit immediately, whenever it
            # occurs — no awareness of price or the coming evening peak. This is
            # how most home systems run today.
            charge = min(surplus, max_charge, (battery_kwh - soc) / rte)
            soc += charge * rte
            grid_export = surplus - charge          # dumps into negative prices too
            discharge = min(deficit, max_discharge, soc)
            soc -= discharge
            grid_import = deficit - discharge

        else:  # optimized
            hour = idx[i].hour
            evening_peak = 17 <= hour <= 23
            day_median = float(price_eur_kwh.median())

            # Charge from solar surplus first.
            charge = min(surplus, max_charge, (battery_kwh - soc) / rte)
            soc += charge * rte
            leftover = surplus - charge

            # Export leftover solar only when the price is positive; during
            # negative prices, hold/curtail rather than pay to export.
            grid_export = leftover if export_price > 0 else 0.0

            # ARBITRAGE: only in the pre-selected cheapest pre-peak hours, and
            # only enough to cover the evening deficit (planned above).
            room = max(0.0, (battery_kwh - soc) / rte)
            headroom_kw = max(0.0, max_charge - charge)
            if idx[i] in arb_hours and room > 0 and headroom_kw > 0:
                grid_charge = min(headroom_kw, room)
                soc += grid_charge * rte
            else:
                grid_charge = 0.0

            # Cover deficit: use the battery during expensive hours, save it
            # (import from cheap grid) during cheap hours.
            # Cover deficit: discharge the battery during the expensive evening
            # peak (what we saved the solar for). In all other hours, import
            # from the grid and preserve charge. Never discharge while we're
            # arbitrage-charging.
            if evening_peak and idx[i] not in arb_hours:
                discharge = min(deficit, max_discharge, soc)
            else:
                discharge = 0.0
            soc -= discharge
            grid_import = (deficit - discharge) + grid_charge

        cost = grid_import * (price + grid_adder) - grid_export * export_price
        rows.append({
            "hour": idx[i].hour,
            "pv_kw": round(pv, 3),
            "load_kw": round(load, 3),
            "price": round(price, 4),
            "soc_kwh": round(soc, 3),
            "charge_kw": round(charge, 3),
            "discharge_kw": round(discharge, 3),
            "import_kw": round(grid_import, 3),
            "export_kw": round(grid_export, 3),
            "cost_eur": round(cost, 4),
        })

    ledger = pd.DataFrame(rows, index=idx)
    total_cost = round(ledger["cost_eur"].sum(), 2)
    self_consumed = float((ledger["pv_kw"] - ledger["export_kw"]).clip(lower=0).sum())
    pv_total = float(ledger["pv_kw"].sum())
    self_consumption_pct = round(100 * self_consumed / pv_total, 1) if pv_total else 0.0
    summary = {
        "total_cost_eur": total_cost,
        "grid_import_kwh": round(ledger["import_kw"].sum(), 2),
        "grid_export_kwh": round(ledger["export_kw"].sum(), 2),
        "self_consumption_pct": self_consumption_pct,
        "pv_total_kwh": round(pv_total, 2),
    }
    return ledger, summary


def recommendations(pv_kw, load_kw, price_eur_kwh, battery_kwh=10.0):
    """Plain-language advice for the day, derived from the inputs."""
    idx = pv_kw.index
    price = price_eur_kwh
    tips = []

    # 1) cheap/negative window -> run shiftable loads
    cheap = price[price <= price.quantile(0.15)]
    if len(cheap):
        hrs = sorted(cheap.index.hour.tolist())
        span = f"{hrs[0]:02d}:00–{hrs[-1]+1:02d}:00"
        neg = price[price < 0]
        if len(neg):
            nh = sorted(neg.index.hour.tolist())
            tips.append(f"⚡ Power is **free or negative** {nh[0]:02d}:00–{nh[-1]+1:02d}:00 — "
                        f"run the dishwasher, washing machine, or EV charging then, "
                        f"and self-consume rather than export.")
        else:
            tips.append(f"⚡ Cheapest power is around {span} — shift heavy appliances "
                        f"or EV charging into this window.")

    # 2) expensive evening peak -> hold battery
    peak = price[price >= price.quantile(0.90)]
    if len(peak):
        ph = sorted(peak.index.hour.tolist())
        tips.append(f"🔋 Most expensive power is {ph[0]:02d}:00–{ph[-1]+1:02d}:00 — "
                    f"keep the battery charged to cover this peak instead of "
                    f"importing from the grid.")

    # 3) midday surplus -> store, don't dump
    midday_pv = pv_kw.between_time("11:00", "15:00").sum()
    if midday_pv > battery_kwh:
        tips.append(f"☀️ Midday solar ({midday_pv:.1f} kWh) exceeds your "
                    f"{battery_kwh:.0f} kWh battery — consider shifting flexible "
                    f"loads to noon so less is exported cheaply.")

    if not tips:
        tips.append("No strong price signals today — a flat day, so standard "
                    "self-consumption is fine.")
    return tips


if __name__ == "__main__":
    import datetime as dt
    from solar import pv_generation, daily_load_profile
    from prices import sample_prices

    day = dt.date.today()
    pv = pv_generation(day, 52.52, 13.405, "Europe/Berlin", kwp=8.0)
    load = daily_load_profile(day, 12.0)
    price = sample_prices(day)

    led_n, sum_n = simulate(pv, load, price, strategy="naive")
    led_o, sum_o = simulate(pv, load, price, strategy="optimized")
    print("NAIVE    ", sum_n)
    print("OPTIMIZED", sum_o)
    saving = round(sum_n["total_cost_eur"] - sum_o["total_cost_eur"], 2)
    print(f"Daily saving: €{saving}  (~€{round(saving*365,0):.0f}/yr)")
    print()
    for t in recommendations(pv, load, price):
        print("-", t)

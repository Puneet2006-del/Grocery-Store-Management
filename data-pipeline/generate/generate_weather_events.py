"""Generate weather.csv and events.csv.

Weather: real historical data from the free Open-Meteo archive API.
         If the API is unreachable (or --offline is passed), a synthetic
         seasonal curve for Delhi NCR is used instead.
Events:  Indian public holidays (python 'holidays' library) + simulated
         local events (cricket matches, concerts).

Run from project root:  python data-pipeline/generate/generate_weather_events.py
"""
import sys

import holidays
import numpy as np
import pandas as pd
import requests

from config import END_DATE, RAW, SEED, START_DATE

rng = np.random.default_rng(SEED)
dates = pd.date_range(START_DATE, END_DATE, freq="D")


# ---------------------------------------------------------------- weather
def fetch_open_meteo(lat: float, lon: float) -> pd.DataFrame:
    url = "https://archive-api.open-meteo.com/v1/archive"
    params = {
        "latitude": lat,
        "longitude": lon,
        "start_date": START_DATE,
        "end_date": END_DATE,
        "daily": "temperature_2m_mean,precipitation_sum",
        "timezone": "Asia/Kolkata",
    }
    r = requests.get(url, params=params, timeout=30)
    r.raise_for_status()
    d = r.json()["daily"]
    return pd.DataFrame(
        {
            "weather_date": pd.to_datetime(d["time"]),
            "temp_c": d["temperature_2m_mean"],
            "rain_mm": d["precipitation_sum"],
        }
    )


def synthetic_weather(city_offset: float) -> pd.DataFrame:
    doy = dates.dayofyear.to_numpy()
    temp = 25 + 11 * np.sin(2 * np.pi * (doy - 64) / 365)   # peak ~June, low ~Dec/Jan
    temp = temp + city_offset + rng.normal(0, 1.5, len(dates))
    # monsoon: Jul-Sep rains often, rest of year rarely
    rain_prob = np.where(dates.month.isin([7, 8, 9]), 0.45, 0.04)
    rain = np.where(rng.random(len(dates)) < rain_prob, rng.gamma(2.0, 8.0, len(dates)), 0.0)
    return pd.DataFrame({"weather_date": dates, "temp_c": temp, "rain_mm": rain})


def build_weather(stores: pd.DataFrame, offline: bool) -> pd.DataFrame:
    cities = stores.groupby("city")[["lat", "lon"]].first().reset_index()
    frames = []
    for i, row in cities.iterrows():
        df = None
        if not offline:
            try:
                df = fetch_open_meteo(row["lat"], row["lon"])
                print(f"  {row['city']}: real data from Open-Meteo")
            except Exception as e:  # network down, API change, etc.
                print(f"  {row['city']}: API failed ({e.__class__.__name__}), using synthetic")
        if df is None:
            df = synthetic_weather(city_offset=i * 0.3)
            print(f"  {row['city']}: synthetic data")
        df["city"] = row["city"]
        frames.append(df)
    w = pd.concat(frames, ignore_index=True)
    w["temp_c"] = w["temp_c"].round(1)
    w["rain_mm"] = w["rain_mm"].fillna(0).round(1)
    w["weather_date"] = pd.to_datetime(w["weather_date"]).dt.date
    return w[["weather_date", "city", "temp_c", "rain_mm"]]


# ----------------------------------------------------------------- events
# Demand multiplier by holiday keyword (default 1.10 for other holidays)
HOLIDAY_IMPACT = {"diwali": 1.40, "holi": 1.30, "dussehra": 1.20, "raksha": 1.20,
                  "christmas": 1.20, "eid": 1.25, "republic": 1.05, "independence": 1.05}


def build_events(cities: list[str]) -> pd.DataFrame:
    years = sorted({d.year for d in dates})
    in_range = holidays.India(years=years)
    rows = []
    for day, name in sorted(in_range.items()):
        if not (dates[0].date() <= day <= dates[-1].date()):
            continue
        impact = next((v for k, v in HOLIDAY_IMPACT.items() if k in name.lower()), 1.10)
        for city in cities:
            rows.append((day, city, "holiday", impact))

    # simulated local events: ~10 per city over the year
    for city in cities:
        picks = rng.choice(dates, size=10, replace=False)
        for d in picks:
            kind = rng.choice(["match", "concert"])
            rows.append((pd.Timestamp(d).date(), city, kind, round(float(rng.uniform(1.08, 1.25)), 2)))

    ev = pd.DataFrame(rows, columns=["event_date", "city", "event_type", "expected_impact"])
    ev = ev.sort_values(["event_date", "city"]).reset_index(drop=True)
    ev.insert(0, "event_id", [f"E{i + 1:04d}" for i in range(len(ev))])
    return ev


# ------------------------------------------------------------------- main
if __name__ == "__main__":
    offline = "--offline" in sys.argv
    stores = pd.read_csv(RAW / "stores.csv")

    print("Weather:")
    weather = build_weather(stores, offline)
    weather.to_csv(RAW / "weather.csv", index=False)

    events = build_events(sorted(stores["city"].unique()))
    events.to_csv(RAW / "events.csv", index=False)

    print(f"\nweather.csv: {len(weather)} rows | events.csv: {len(events)} rows")
    print(events.groupby("event_type").size().to_string())

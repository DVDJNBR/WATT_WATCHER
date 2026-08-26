"""Generate ERA5 sample Parquet fixture for tests — Story 2.2"""

import polars as pl
from datetime import datetime

# Simulated ERA5 hourly data for 3 French regions, 48 hours
# Variables: u100, v100 (wind components at 100m), ssrd (solar radiation), t2m (surface temp)

regions = [
    {"latitude": 48.86, "longitude": 2.35, "region_code": "11"},   # Île-de-France
    {"latitude": 45.76, "longitude": 4.83, "region_code": "84"},   # Auvergne-Rhône-Alpes
    {"latitude": 43.30, "longitude": 5.37, "region_code": "93"},   # PACA
]

rows = []
base = datetime(2025, 6, 15, 0, 0, 0)

for hour in range(48):
    ts = datetime(2025, 6, 15 + hour // 24, hour % 24, 0, 0)
    for r in regions:
        import random
        random.seed(hour * 100 + int(r["region_code"]))
        rows.append({
            "valid_time": ts,
            "latitude": r["latitude"],
            "longitude": r["longitude"],
            "u100": round(random.uniform(-8, 12), 2),    # m/s
            "v100": round(random.uniform(-6, 8), 2),     # m/s
            "ssrd": round(random.uniform(0, 25000), 1),  # J/m² (cumulative)
            "t2m": round(random.uniform(285, 310), 2),   # Kelvin
        })

df = pl.DataFrame(rows)
df.write_parquet("tests/fixtures/era5_sample.parquet")
print(f"Written {len(df)} rows to tests/fixtures/era5_sample.parquet")
print(df.head(5))

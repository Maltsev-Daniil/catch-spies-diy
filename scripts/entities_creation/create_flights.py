from pathlib import Path

import pandas as pd

BASE_DIR = Path(__file__).resolve().parent
SOURCE_DIR = BASE_DIR.parent / "lake" / "done_tables"
OUTPUT_DIR = BASE_DIR / "bd_tables"

KEY_COLUMNS = [
    "FlightNumber",
    "FlightDate",
    "OriginAirport",
    "DestinationAirport",
]

DETAIL_COLUMNS = [
    "OriginCountry",
    "OriginCity",
    "DestinationCountry",
    "DestinationCity",
]

OUTPUT_COLUMNS = [
    "FlightNumber",
    "FlightDate",
    "OriginCountry",
    "OriginCity",
    "OriginAirport",
    "DestinationCountry",
    "DestinationCity",
    "DestinationAirport",
]

tables = []
for filename in ("forum_json.csv", "skyteam_yaml.csv"):
    table = pd.read_csv(
        SOURCE_DIR / filename,
        usecols=OUTPUT_COLUMNS,
        dtype="string",
        keep_default_na=False,
    )

    for column in OUTPUT_COLUMNS:
        table[column] = table[column].str.strip().replace("", pd.NA)

    tables.append(table)

flights = (
    pd.concat(tables, ignore_index=True)
    .dropna(subset=KEY_COLUMNS)
    .groupby(KEY_COLUMNS, as_index=False, sort=False)
    .agg({column: "first" for column in DETAIL_COLUMNS})
)

OUTPUT_DIR.mkdir(exist_ok=True)
flights.to_csv(
    OUTPUT_DIR / "flights.csv",
    columns=OUTPUT_COLUMNS,
    index=False,
    encoding="utf-8",
)

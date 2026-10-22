from pathlib import Path

import pandas as pd

BASE_DIR = Path(__file__).resolve().parent
SOURCE_FILE = BASE_DIR.parent / "lake" / "done_tables" / "sirena_tab.csv"
OUTPUT_DIR = BASE_DIR / "bd_tables"
OUTPUT_DIR.mkdir(exist_ok=True)

df = pd.read_csv(
    SOURCE_FILE,
    usecols=["PassengerDocument", "FrequentFlyer"],
    dtype="string",
    keep_default_na=False,
)

df["PassengerDocument"] = df["PassengerDocument"].str.strip()

parts = df["FrequentFlyer"].str.strip().str.split(n=1, expand=True)
df["ProgramCode"] = parts[0].str.upper()
df["CardNumber"] = parts[1].str.strip()

df = df[
    df["PassengerDocument"].ne("")
    & df["ProgramCode"].str.fullmatch(r"[A-Z]{2,3}").fillna(False)
    & df["CardNumber"].str.fullmatch(r"\d+").fillna(False)
].copy()

loyalty = df[
    ["PassengerDocument", "CardNumber", "ProgramCode"]
].drop_duplicates()

loyalty.to_csv(
    OUTPUT_DIR / "loyalty.csv",
    index=False,
    encoding="utf-8",
)

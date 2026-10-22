from pathlib import Path

import pandas as pd

BASE_DIR = Path(__file__).resolve().parent
SOURCE_DIR = BASE_DIR.parent / "lake" / "done_tables"
OUTPUT_DIR = BASE_DIR / "bd_tables"

NAME_COLUMNS = [
    "PassengerFirstName",
    "PassengerSecondName",
    "PassengerLastName",
]
OUTPUT_COLUMNS = NAME_COLUMNS + [
    "PassengerDocument",
    "PassengerBirthDate",
]

df = pd.concat(
    [
        pd.read_csv(
            SOURCE_DIR / filename,
            usecols=list(OUTPUT_COLUMNS),
            dtype="string",  # Сохраняем ведущие нули в паспортах.
            keep_default_na=False,
            )
        for filename in ("sirena_tab.csv", "boarding_csv.csv")
    ],
    ignore_index=True,
)

for column in OUTPUT_COLUMNS:
    df[column] = df[column].str.strip().replace("", pd.NA)

# Паспорт и дата рождения должны происходить из одной исходной строки.
# Одинаковое ФИО может принадлежать разным людям, поэтому не объединяем
# записи по ФИО и сохраняем разные даты рождения одного паспорта для проверки.
identity_columns = NAME_COLUMNS + ["PassengerDocument"]
df = df.dropna(subset=NAME_COLUMNS, how="all").dropna(subset=["PassengerDocument"])
has_known_birth = (
    df.groupby(identity_columns, dropna=False)["PassengerBirthDate"]
    .transform("count")
    .gt(0)
)
passangers = df[
    df["PassengerBirthDate"].notna() | ~has_known_birth
].drop_duplicates(subset=OUTPUT_COLUMNS)

passangers.to_csv(
    OUTPUT_DIR / "passangers.csv",
    columns=list(OUTPUT_COLUMNS),
    index=False,
    encoding="utf-8",
)

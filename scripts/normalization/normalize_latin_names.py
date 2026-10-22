
import re
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd


BASE = Path(__file__).resolve().parent / "done_tables"

FILES = [
    "sirena_tab.csv",
    "boarding_xlsx.csv",
    "pointz_xml.csv",
    "boarding_csv.csv",
    "forum_json.csv",
]

NAME_COLUMNS = (
    "PassengerFullName",
    "PassengerFirstName",
    "PassengerSecondName",
    "PassengerLastName",
)

WORKERS = min(len(FILES), 8)


def skeleton(word):
    """Сводит варианты транслитерации к одному виду."""
    s = (
        word.upper()
        .replace("'", "")
        .replace("Y", "I")
        .replace("TC", "TS")
        .replace("KH", "H")
        .replace("IE", "E")
        .replace("KS", "X")
    )
    return re.sub(r"I+", "I", s)


def normalize_name(value):
    """Нормализует имя; пустые значения оставляет без изменений."""
    if not value:
        return value

    return skeleton(value)


def process_file(filename):
    path = BASE / filename

    if not path.is_file():
        raise FileNotFoundError(f"Файл не найден: {path}")

    # Читаем все поля как строки, сохраняя пустые значения
    df = pd.read_csv(
        path,
        dtype=str,
        keep_default_na=False,
    )

    # Обрабатываем только те столбцы, которые есть в файле
    for column in NAME_COLUMNS:
        if column not in df.columns:
            continue

        df[column] = df[column].map(normalize_name)

    # Записываем во временный файл, затем заменяем оригинал
    temp_path = path.with_suffix(path.suffix + ".tmp")

    try:
        df.to_csv(temp_path, index=False)
        temp_path.replace(path)
    finally:
        temp_path.unlink(missing_ok=True)

    return filename, len(df)


def main():
    if not BASE.is_dir():
        raise FileNotFoundError(f"Папка не найдена: {BASE}")

    with ThreadPoolExecutor(max_workers=WORKERS) as executor:
        futures = {
            executor.submit(process_file, filename): filename
            for filename in FILES
        }

        for future in as_completed(futures):
            filename = futures[future]

            try:
                name, count = future.result()
                print(f"[OK] {name}: обработано {count} строк")
            except Exception as error:
                print(f"[ERROR] {filename}: {error}")


if __name__ == "__main__":
    main()


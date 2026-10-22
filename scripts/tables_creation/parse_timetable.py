import argparse
import csv
import json
import os
import re
import subprocess
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path

BASE = Path(__file__).resolve().parent
INPUT = BASE / "data/Airlines/Skyteam_Timetable.pdf"
OUTPUT = BASE / "timetable.csv"
COLUMNS = (
    "SourceFile,SourcePage,SourceRecord,OriginCity,OriginCountry,OriginAirport,"
    "DestinationCity,DestinationCountry,DestinationAirport,ValidFrom,ValidTo,"
    "OperatingDays,FlightTime,ArrivalTime,ArrivalDayOffset,FlightNumber,"
    "AircraftType,TravelTime,RawRecord"
).split(",")
MONTHS = {name: number for number, name in enumerate(
    "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split(), 1)}
DATE = r"\d{1,2}\s+[A-Za-z]{3}"
TIME = r"(?:[01]\d|2[0-3]):[0-5]\d"
FLIGHT_ROW = re.compile(
    rf"^({DATE})\s*-\s*({DATE})\s+([1-7 ]+?)\s+({TIME})\s+"
    rf"({TIME})\s*(\+-\d+|[+-]\d+)?\s+([A-Z0-9]+\*?)\s+(\S+)\s+(\d+H\d+M)\s*$"
)
ROUTE = re.compile(r"^(FROM|TO):\s*(.+?)\s+([A-Z0-9]{3})\s*$")


def command(args):
    result = subprocess.run(args, capture_output=True, text=True, encoding="utf-8")
    if result.returncode:
        raise ValueError(result.stderr.strip())
    return result.stdout


def extract(path, first, last, crop=None):
    args = ["pdftotext", "-f", str(first), "-l", str(last), "-r", "72", "-layout"]
    if crop:
        x, width, height = crop
        args += ["-x", str(x), "-y", "0", "-W", str(width), "-H", str(height)]
    return command(args + [str(path), "-"])


def cpu_count():
    if hasattr(os, "sched_getaffinity"):
        return len(os.sched_getaffinity(0)) or 1
    return os.cpu_count() or 1


def extract_chunk(path, first, last):
    columns = [extract(path, first, last, crop).split("\f")
               for crop in ((0, 297, 842), (297, 298, 842))]
    if any(len(pages) != last - first + 2 or pages[-1].strip() for pages in columns):
        raise ValueError(f"Страницы {first}–{last}: неожиданное число страниц после извлечения")
    return first, last, columns


def extracted_chunks(path, page_count, workers, chunk_size=100):
    chunks = iter((first, min(first + chunk_size - 1, page_count))
                  for first in range(5, page_count + 1, chunk_size))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        pending = deque()
        for first, last in chunks:
            pending.append(pool.submit(extract_chunk, path, first, last))
            if len(pending) == workers:
                break
        while pending:
            result = pending.popleft().result()
            yield result
            next_chunk = next(chunks, None)
            if next_chunk is not None:
                pending.append(pool.submit(extract_chunk, path, *next_chunk))


def full_date(day_month, year):
    day, month = day_month.split()
    return date(year, MONTHS[month.title()], int(day))


def resolve_date(day_month, period_start, period_end):
    candidate = full_date(day_month, period_start.year)
    if candidate < period_start:
        candidate = full_date(day_month, period_start.year + 1)
    return candidate


def parse_column(text, route, page, side, source, period):
    rows = []
    for line_number, original in enumerate(text.splitlines(), 1):
        line = original.strip()
        if not line:
            continue
        location = f"page:{page}/{side}/line:{line_number}"
        header = ROUTE.fullmatch(line)
        if header:
            direction, place, airport = header.groups()
            city, country = place.rsplit(",", 1) if "," in place else ("", "")
            if direction == "FROM":
                route.clear()
            prefix = "Origin" if direction == "FROM" else "Destination"
            route.update({prefix + "City": city.strip(), prefix + "Country": country.strip(),
                          prefix + "Airport": airport})
            route[prefix + "Raw"] = place.strip()
            continue
        if line.startswith(("FROM:", "TO:")):
            raise ValueError(f"{location}: не удалось разобрать маршрут: {line}")
        match = FLIGHT_ROW.fullmatch(line)
        if not match:
            if re.match(r"^\d{1,2}\s+[A-Za-z]{3}\s*-", line) or re.search(TIME, line):
                raise ValueError(f"{location}: не удалось разобрать строку расписания: {line}")
            if line.startswith("Operated by:") and rows:
                raw = json.loads(rows[-1]["RawRecord"])
                raw["Notes"] = raw.get("Notes", []) + [line]
                rows[-1]["RawRecord"] = json.dumps(raw, ensure_ascii=False)
                continue
            if (line.startswith("Validity")
                    or re.fullmatch(r"Time(?:\s+Time)*", line)
                    or line == "Consult your travel agent for details"):
                continue
            raise ValueError(f"{location}: неизвестная строка, проверьте её вручную: {line}")
        if not all(key in route for key in ("OriginAirport", "DestinationAirport")):
            raise ValueError(f"{location}: у рейса отсутствует полный маршрут")
        start, end, days, departure, arrival, offset, flight, aircraft, duration = match.groups()
        start_date = resolve_date(start, *period)
        end_date = resolve_date(end, *period)
        row = {key: value for key, value in route.items() if key in COLUMNS}
        row.update(SourceFile=source, SourcePage=page, SourceRecord=location,
                   ValidFrom=start_date.isoformat(), ValidTo=end_date.isoformat(),
                   OperatingDays=days.replace(" ", ""), FlightTime=departure,
                   ArrivalTime=arrival, ArrivalDayOffset=int((offset or "0").replace("+-", "-")),
                   FlightNumber=flight, AircraftType=aircraft, TravelTime=duration,
                   RawRecord=json.dumps({"Line": original, "Route": dict(route),
                                         "Flight": flight}, ensure_ascii=False))
        rows.append(row)
    return rows


def convert(input_path=INPUT, output_path=OUTPUT, workers=None):
    workers = cpu_count() if workers is None else workers
    if workers < 1:
        raise ValueError("Число workers должно быть положительным")
    input_path, output_path = Path(input_path).resolve(), Path(output_path).resolve()
    if input_path == output_path:
        raise ValueError("Входной и выходной файлы должны отличаться")
    info = command(["pdfinfo", str(input_path)])
    page_count = int(re.search(r"Pages:\s+(\d+)", info).group(1))
    cover = extract(input_path, 1, 1)
    dates = re.search(rf"Covers period:\s*({DATE})\s+(\d{{4}})\s+through\s+({DATE})\s+(\d{{4}})", cover)
    start, year1, end, year2 = dates.groups()
    period = (full_date(start, int(year1)), full_date(end, int(year2)))
    source = input_path.relative_to(BASE).as_posix() if BASE in input_path.parents else input_path.as_posix()
    routes = [{}, {}]
    count = 0
    print(f"Параллельных задач: {workers}; страниц: {page_count}", flush=True)
    with output_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=COLUMNS, lineterminator="\n")
        writer.writeheader()
        for first, last, columns in extracted_chunks(input_path, page_count, workers):
            for index, page in enumerate(range(first, last + 1)):
                for side, label in enumerate(("left", "right")):
                    rows = parse_column(columns[side][index], routes[side], page, label, source, period)
                    writer.writerows(rows)
                    count += len(rows)
            stream.flush()
            print(f"Страницы: {last}/{page_count}; записано строк: {count}", flush=True)
    return count


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=INPUT)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--workers", type=int, default=None,
                        help="Число параллельных задач; по умолчанию все доступные ядра")
    args = parser.parse_args()
    print(f"Готово: {convert(args.input, args.output, args.workers)} строк → {args.output}")

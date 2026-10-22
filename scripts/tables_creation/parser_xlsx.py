import argparse
import csv
import json
import re
import sys
from datetime import datetime
from pathlib import Path

import openpyxl

BASE = Path(__file__).resolve().parent

COLUMNS = (
    "SourceType,SourceFile,SourceSheet,SourceRecord,SourceEntityId,UserId,NickName,"
    "PassengerTitle,PassengerFullName,PassengerFirstName,PassengerSecondName,"
    "PassengerLastName,PassengerSex,PassengerBirthDate,PassengerDocument,Passports,"
    "BookingCode,TicketNumber,FrequentFlyer,BonusProgramCode,FrequentFlyerNumber,"
    "BonusProgram,FrequentFlyerStatus,LoyaltyPrograms,CardType,ActivitiesType,"
    "ActivityType,FlightDate,FlightTime,ArrivalDate,ArrivalTime,FlightNumber,CodeShare,"
    "OriginCity,OriginCountry,OriginAirport,DestinationCity,DestinationCountry,"
    "DestinationAirport,DestinationRaw,TravelClass,Fare,FlightStatus,Gate,Seat,"
    "BoardingSequence,Baggage,Meal,OperatorNote,PaxAdditionalInfo,AgentInfo,"
    "UnmappedFields,RawRecord"
).split(",")

LOG_HEADERS = ["SourceType", "SourceFile", "SourceRecord", "Field", "Issue", "Action"]

INPUT_DIR = BASE / "Билеты"
OUTPUT = BASE / "boarding_xlsx.csv"
LOG = BASE / "boarding_xlsx_issues.csv"
REPORT = BASE / "boarding_xlsx_report.txt"

SOURCE_TYPE = "boarding_xlsx"

CELL_MAP = {
    "PassengerTitle":    ("A3",  None,        None),
    "PassengerFullName": ("B3",  None,        None),
    "FlightNumber":      ("A5",  None,        None),
    "OriginCity":        ("D5",  None,        None),
    "DestinationCity":   ("H5",  None,        None),
    "OriginAirport":     ("D7",  None,        None),
    "DestinationAirport":("H7",  None,        None),
    "FlightDate":        ("A9",  None,        None),
    "FlightTime":        ("C9",  None,        None),
    "OperatorNote":      ("E9",  None,        None),
    "Seat":              ("H11", "SEAT",      "G11"),
    "BookingCode":       ("B13", "PNR:",      "A13"),
    "TicketNumber":      ("F13", "E-TICKET",  "D13"),
    "BoardingSequence":  ("H1",  "SEQUENCE:", "F1"),
    "TravelClass":       ("H3",  None,        None),
    "Gate":              ("B7",  "GATE",      "A7"),
    "FrequentFlyer":     ("F3",  None,        None),
}

def make_log(quiet=False, verbose=True):
    def log(msg, level="info"):
        if quiet and level not in ("error", "result"):
            return
        if level == "trace" and not verbose:
            return
        prefix = {
            "info":   "[INFO]",
            "trace":  "[TRACE]",
            "warn":   "[WARN]",
            "error":  "[ERROR]",
            "result": "[RESULT]",
        }.get(level, "[LOG]")
        print(f"{prefix} {msg}", file=sys.stderr if level == "error" else sys.stdout, flush=True)
    return log

def clean(value):
    if value is None:
        return ""
    return str(value).strip()


def is_na(value):
    return clean(value).upper() in ("N/A", "NA", "NONE", "NULL", "-", "—")


def format_date(value):
    if not value or is_na(value):
        return ""
    value = clean(value)
    for pattern in ("%Y-%m-%d", "%m/%d/%Y", "%d.%m.%Y", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(value, pattern).strftime("%Y-%m-%d")
        except ValueError:
            pass
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", value)
    if m:
        try:
            return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3))).strftime("%Y-%m-%d")
        except ValueError:
            pass
    raise ValueError(f"Неизвестный формат даты: {value!r}")

def parse_sheet(ws, sheet_name, source_file, issues, log):
    record_id = f"sheet:{sheet_name}"
    log(f"Лист {sheet_name!r}: диапазон {ws.dimensions}", "info")

    a1 = clean(ws["A1"].value)
    log(f"  A1 = {a1!r}", "trace")
    if "BOARDING PASS" not in a1.upper():
        log(f"  A1 не содержит 'BOARDING PASS' → лист пропущен", "warn")
        issues.append({
            "SourceType": SOURCE_TYPE,
            "SourceFile": source_file,
            "SourceRecord": record_id,
            "Field": "A1",
            "Issue": f"Лист не является посадочным талоном (A1={a1!r})",
            "Action": "Лист пропущен",
        })
        return None

    row = {column: "" for column in COLUMNS}
    raw = {}
    unmapped = {}

    for target, (cell, expected_label, label_cell) in CELL_MAP.items():
        value = ws[cell].value
        raw[cell] = clean(value)
        log(f"  {cell} (→ {target}) = {clean(value)!r}", "trace")

        if expected_label and label_cell:
            label_value = clean(ws[label_cell].value)
            log(f"    подпись {label_cell} = {label_value!r}, ожидалось {expected_label!r}", "trace")
            if expected_label.upper() not in label_value.upper():
                log(f"    подпись не совпала → в журнал", "warn")
                issues.append({
                    "SourceType": SOURCE_TYPE,
                    "SourceFile": source_file,
                    "SourceRecord": record_id,
                    "Field": cell,
                    "Issue": f"Ожидалась подпись {expected_label!r} в {label_cell}, получено {label_value!r}",
                    "Action": "Значение извлечено по координате, подпись не совпала",
                })

        if is_na(value):
            log(f"    значение N/A → пусто", "trace")
            value = ""
        row[target] = clean(value)

    seq_val = clean(ws["H1"].value)
    log(f"  H1 (→ BoardingSequence) = {seq_val!r}", "trace")
    if seq_val:
        m = re.search(r"\d+", seq_val)
        row["BoardingSequence"] = m.group(0) if m else seq_val

    try:
        row["FlightDate"] = format_date(row["FlightDate"])
        log(f"  FlightDate нормализовано → {row['FlightDate']!r}", "trace")
    except ValueError as e:
        log(f"  FlightDate: {e}", "warn")
        issues.append({
            "SourceType": SOURCE_TYPE,
            "SourceFile": source_file,
            "SourceRecord": record_id,
            "Field": "FlightDate",
            "Issue": str(e),
            "Action": "Нормализованное поле пусто, оригинал в RawRecord",
        })
        row["FlightDate"] = ""

    ff = row.get("FrequentFlyer", "")
    if ff:
        row["LoyaltyPrograms"] = json.dumps([{"FrequentFlyer": ff}], ensure_ascii=False)
        log(f"  FrequentFlyer = {ff!r} → LoyaltyPrograms заполнено", "trace")
    else:
        row["LoyaltyPrograms"] = "[]"
        log(f"  FrequentFlyer пусто → LoyaltyPrograms = []", "trace")

    row["SourceType"] = SOURCE_TYPE
    row["SourceFile"] = source_file
    row["SourceSheet"] = sheet_name
    row["SourceRecord"] = record_id

    used_cells = set()
    for target, (cell, _, label_cell) in CELL_MAP.items():
        used_cells.add(cell)
        if label_cell:
            used_cells.add(label_cell)
    used_cells.add("A1")

    for row_cells in ws.iter_rows():
        for cell in row_cells:
            coord = cell.coordinate
            if coord not in used_cells and cell.value is not None and clean(cell.value):
                unmapped[coord] = clean(cell.value)

    if unmapped:
        log(f"  UnmappedFields: {json.dumps(unmapped, ensure_ascii=False)}", "info")
    row["UnmappedFields"] = json.dumps(unmapped, ensure_ascii=False) if unmapped else ""

    raw_record = {"sheet": sheet_name, "cells": raw, "unmapped": unmapped}
    row["RawRecord"] = json.dumps(raw_record, ensure_ascii=False)

    log(
        "  → строка: "
        f"FIO={row['PassengerFullName']!r}, "
        f"Flight={row['FlightNumber']!r}, "
        f"{row['OriginAirport']}->{row['DestinationAirport']}, "
        f"Date={row['FlightDate']!r} {row['FlightTime']!r}, "
        f"PNR={row['BookingCode']!r}, "
        f"Ticket={row['TicketNumber']!r}, "
        f"Seat={row['Seat']!r}, "
        f"Gate={row['Gate']!r}, "
        f"Seq={row['BoardingSequence']!r}",
        "info"
    )
    return row

def convert(input_dir=INPUT_DIR, output_path=OUTPUT, log_path=LOG,
            report_path=REPORT, quiet=False, verbose=True):
    log = make_log(quiet=quiet, verbose=verbose)

    input_dir = Path(input_dir).resolve()
    output_path = Path(output_path).resolve()
    log_path = Path(log_path).resolve()
    report_path = Path(report_path).resolve()

    log(f"Входная папка: {input_dir}", "info")
    log(f"Выходной CSV:  {output_path}", "info")
    log(f"Журнал:        {log_path}", "info")
    log(f"Отчёт:         {report_path}", "info")

    if not input_dir.is_dir():
        raise ValueError(f"Папка не найдена: {input_dir}")

    files = sorted(input_dir.glob("*.xlsx")) + sorted(input_dir.glob("*.xlsm"))
    log(f"Найдено файлов: {len(files)}", "info")
    for f in files:
        log(f"  - {f.name}", "info")
    if not files:
        print("Не найдено Excel-файлов.")
        return

    all_rows = []
    all_issues = []
    files_processed = 0
    sheets_total = 0
    sheets_written = 0
    sheets_skipped = 0

    for file_path in files:
        rel_path = file_path.relative_to(BASE).as_posix() if BASE in file_path.parents else file_path.as_posix()
        log(f"Открываю файл: {rel_path}", "info")
        try:
            wb = openpyxl.load_workbook(file_path, data_only=True)
        except Exception as e:
            log(f"  ошибка открытия: {e}", "error")
            all_issues.append({
                "SourceType": SOURCE_TYPE,
                "SourceFile": rel_path,
                "SourceRecord": "",
                "Field": "",
                "Issue": f"Ошибка открытия файла: {e}",
                "Action": "Файл пропущен",
            })
            continue

        files_processed += 1
        log(f"  листов в файле: {len(wb.sheetnames)} → {wb.sheetnames}", "info")

        for sheet_name in wb.sheetnames:
            ws = wb[sheet_name]
            sheets_total += 1
            try:
                row = parse_sheet(ws, sheet_name, rel_path, all_issues, log)
                if row is None:
                    sheets_skipped += 1
                    continue
                all_rows.append(row)
                sheets_written += 1
            except Exception as e:
                log(f"  ошибка обработки листа {sheet_name!r}: {e}", "error")
                all_issues.append({
                    "SourceType": SOURCE_TYPE,
                    "SourceFile": rel_path,
                    "SourceRecord": f"sheet:{sheet_name}",
                    "Field": "",
                    "Issue": f"Ошибка обработки листа: {e}",
                    "Action": "Лист пропущен",
                })
                sheets_skipped += 1

    log(f"Записываю CSV: {output_path}", "info")
    with output_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(all_rows)

    log(f"Записываю журнал: {log_path}", "info")
    with log_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=LOG_HEADERS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(all_issues)

    log(f"Записываю отчёт: {report_path}", "info")
    with report_path.open("w", encoding="utf-8") as f:
        f.write("ОТЧЁТ О ПРОВЕРКЕ\n")
        f.write("=" * 60 + "\n")
        f.write(f"Обработано файлов: {files_processed}\n")
        f.write(f"Всего листов: {sheets_total}\n")
        f.write(f"Записано строк (валидных листов): {sheets_written}\n")
        f.write(f"Пропущено листов: {sheets_skipped}\n")
        f.write(f"Проблем в журнале: {len(all_issues)}\n")

    log(f"Готово: {len(all_rows)} строк → {output_path}", "result")
    log(f"Журнал: {log_path}", "result")
    log(f"Отчёт: {report_path}", "result")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=INPUT_DIR)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--log", type=Path, default=LOG)
    parser.add_argument("--report", type=Path, default=REPORT)
    parser.add_argument("--quiet", action="store_true",
                        help="Печатать только предупреждения, ошибки и итог")
    parser.add_argument("--verbose", action="store_true", default=True,
                        help="Подробный лог по ячейкам (по умолчанию включён)")
    parser.add_argument("--no-verbose", dest="verbose", action="store_false",
                        help="Отключить лог по ячейкам")
    args = parser.parse_args()

    convert(
        input_dir=args.input,
        output_path=args.output,
        log_path=args.log,
        report_path=args.report,
        quiet=args.quiet,
        verbose=args.verbose,
    )


if __name__ == "__main__":
    main()
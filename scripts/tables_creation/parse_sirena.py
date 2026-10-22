import re
import csv
import json
from datetime import datetime
from pathlib import Path

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


def format_date(value):
    if value in ("", "N/A"):
        return ""
    for pattern in ("%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(value, pattern).strftime("%Y-%m-%d")
        except ValueError:
            pass
    raise ValueError(f"Неизвестный формат даты: {value!r}")

INPUT = BASE / "data/Airlines/Sirena-export-fixed.tab"
OUTPUT = BASE / "sirena_tab.csv"

FIELDS = [
    ("PaxName", 0, "PassengerFullName"),
    ("PaxBirthDate", 60, "PassengerBirthDate"),
    ("DepartDate", 72, "FlightDate"),
    ("DepartTime", 84, "FlightTime"),
    ("ArrivalDate", 96, "ArrivalDate"),
    ("ArrivalTime", 108, "ArrivalTime"),
    ("Flight", 120, "FlightNumber"),
    ("CodeSh", 126, "CodeShare"),
    ("From", 132, "OriginAirport"),
    ("Dest", 138, "DestinationAirport"),
    ("Code", 144, "BookingCode"),
    ("e-Ticket", 150, "TicketNumber"),
    ("TravelDoc", 168, "PassengerDocument"),
    ("Seat", 180, "Seat"),
    ("Meal", 186, "Meal"),
    ("TrvCls", 192, "TravelClass"),
    ("Fare", 198, "Fare"),
    ("Baggage", 204, "Baggage"),
    ("PaxAdditionalInfo", 216, "PaxAdditionalInfo"),
    ("AgentInfo", 276, "AgentInfo"),
]


def convert(input_path=INPUT, output_path=OUTPUT):
    input_path, output_path = Path(input_path).resolve(), Path(output_path).resolve()
    if input_path == output_path:
        raise ValueError("Входной и выходной файлы должны отличаться")
    source = input_path.relative_to(BASE).as_posix() if BASE in input_path.parents else input_path.as_posix()
    temporary = output_path.with_suffix(".csv.tmp")
    count = 0
    try:
        with input_path.open(encoding="utf-8-sig") as src, temporary.open("w", encoding="utf-8", newline="") as dst:
            header = src.readline().rstrip("\r\n")
            for index, (name, start, target) in enumerate(FIELDS):
                end = FIELDS[index + 1][1] if index + 1 < len(FIELDS) else None
                if header[start:end].strip() != name:
                    raise ValueError(f"Неожиданная структура заголовка около {name}")
            writer = csv.DictWriter(dst, fieldnames=COLUMNS, lineterminator="\n")
            writer.writeheader()

            for number, line in enumerate(src, 1):
                line = line.rstrip("\r\n")
                if not line.strip():
                    continue
                if len(line) < 72 or "\t" in line:
                    raise ValueError(f"Запись {number}: неверная структура строки")
                row = {column: "" for column in COLUMNS}
                raw = {}
                for index, (name, start, target) in enumerate(FIELDS):
                    end = FIELDS[index + 1][1] if index + 1 < len(FIELDS) else None
                    value = line[start:end].strip()
                    raw[name] = value
                    row[target] = "" if value == "N/A" else value
                for column in ("PassengerBirthDate", "FlightDate", "ArrivalDate"):
                    row[column] = format_date(row[column])

                cards = re.findall(r"FF#([A-Za-z0-9]{2})\s+(\d+)\b", row["PaxAdditionalInfo"])
                if len(cards) == 1:
                    program, card_number = cards[0]
                    row["FrequentFlyer"] = f"{program} {card_number}"
                    row["BonusProgramCode"] = program
                    row["FrequentFlyerNumber"] = card_number
                elif cards:
                    row["LoyaltyPrograms"] = json.dumps([
                        {"BonusProgramCode": program, "FrequentFlyerNumber": card_number}
                        for program, card_number in cards
                    ], ensure_ascii=False)
                row["SourceType"] = "sirena_tab"
                row["SourceFile"] = source
                row["SourceRecord"] = f"row:{number}"
                row["RawRecord"] = json.dumps(raw, ensure_ascii=False)
                writer.writerow(row)
                count += 1
        temporary.replace(output_path)
    finally:
        temporary.unlink(missing_ok=True)
    return count


if __name__ == "__main__":
    print(f"Готово: {convert()} строк → {OUTPUT}")

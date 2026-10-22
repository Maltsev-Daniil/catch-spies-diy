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

INPUT = BASE / "data/Airlines/BoardingData.csv"
OUTPUT = BASE / "boarding_csv.csv"


def convert(input_path=INPUT, output_path=OUTPUT):
    input_path, output_path = Path(input_path).resolve(), Path(output_path).resolve()
    if input_path == output_path:
        raise ValueError("Входной и выходной файлы должны отличаться")
    source = input_path.relative_to(BASE).as_posix() if BASE in input_path.parents else input_path.as_posix()
    temporary = output_path.with_suffix(".csv.tmp")
    count = 0
    try:
        with input_path.open(encoding="utf-8-sig", newline=None) as src, temporary.open("w", encoding="utf-8", newline="") as dst:
            reader = csv.DictReader(src, delimiter=";", strict=True)
            if not reader.fieldnames or len(set(reader.fieldnames)) != len(reader.fieldnames):
                raise ValueError("Отсутствующий или повторяющийся заголовок")
            writer = csv.DictWriter(dst, fieldnames=COLUMNS, lineterminator="\n")
            writer.writeheader()

            for number, raw in enumerate(reader, 1):
                if None in raw or any(value is None for value in raw.values()):
                    raise ValueError(f"Запись {number}: неверное количество полей")
                row = {column: "" for column in COLUMNS}
                for column, value in raw.items():
                    if column in row:
                        row[column] = value.strip()

                names = ("PassengerLastName", "PassengerFirstName", "PassengerSecondName")
                row["PassengerFullName"] = " ".join(raw.get(name, "").strip() for name in names if raw.get(name, "").strip())
                for column in ("PassengerBirthDate", "FlightDate", "ArrivalDate"):
                    row[column] = format_date(row[column])

                row["DestinationRaw"] = raw.get("Destination", "").strip()
                row["SourceType"] = "boarding_csv"
                row["SourceFile"] = source
                row["SourceRecord"] = f"row:{number}"
                row["RawRecord"] = json.dumps(raw, ensure_ascii=False)
                unknown = {key: value for key, value in raw.items() if key not in COLUMNS and key != "Destination"}
                row["UnmappedFields"] = json.dumps(unknown, ensure_ascii=False) if unknown else ""
                writer.writerow(row)
                count += 1
        temporary.replace(output_path)
    finally:
        temporary.unlink(missing_ok=True)
    return count


if __name__ == "__main__":
    print(f"Готово: {convert()} строк → {OUTPUT}")

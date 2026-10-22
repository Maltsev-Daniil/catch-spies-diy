import csv
import json
import xml.etree.ElementTree as ET
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

KNOWN_ACTIVITY_TAGS = {"Code", "Date", "Departure", "Arrival", "Fare"}


def format_date(value):
    if value in ("", "N/A"):
        return ""
    for pattern in ("%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(value, pattern).strftime("%Y-%m-%d")
        except ValueError:
            pass
    raise ValueError(f"Неизвестный формат даты: {value!r}")


def clean(value):
    return value.strip() if value else ""


def airport(value):
    value = clean(value)
    return value.upper() if value else ""


INPUT = BASE / "fil.xml"
OUTPUT = BASE / "pointz_xml.csv"


def build_row(activity, uid, first, last, full, cards_type, card_number,
              program, activities_type, record, source):
    activity_type = activity.get("type", "") or ""
    code = clean(activity.findtext("Code"))
    date_raw = clean(activity.findtext("Date"))
    departure = clean(activity.findtext("Departure"))
    arrival = clean(activity.findtext("Arrival"))
    fare = clean(activity.findtext("Fare"))

    unmapped = {}
    for child in activity:
        if child.tag not in KNOWN_ACTIVITY_TAGS:
            unmapped[child.tag] = clean(child.text) if child.text else ""

    raw = {
        "user": {"@uid": uid, "name": {"@first": first, "@last": last}},
        "cards": {"@type": cards_type},
        "card": {"@number": card_number, "bonusprogramm": program},
        "activities": {"@type": activities_type},
        "activity": {
            "@type": activity_type,
            "Code": code,
            "Date": date_raw,
            "Departure": departure,
            "Arrival": arrival,
            "Fare": fare,
        },
    }

    row = {column: "" for column in COLUMNS}
    row["SourceType"] = "pointz_xml"
    row["SourceFile"] = source
    row["SourceRecord"] = record
    row["SourceEntityId"] = uid
    row["UserId"] = uid
    row["PassengerFullName"] = full
    row["PassengerFirstName"] = first
    row["PassengerLastName"] = last
    row["Passports"] = "[]"
    row["FrequentFlyer"] = program
    row["FrequentFlyerNumber"] = card_number
    row["BonusProgram"] = program
    row["LoyaltyPrograms"] = json.dumps([
        {
            "FrequentFlyerNumber": card_number,
            "BonusProgram": program,
            "CardType": cards_type,
        }
    ], ensure_ascii=False)
    row["CardType"] = cards_type
    row["ActivitiesType"] = activities_type
    row["ActivityType"] = activity_type
    row["FlightDate"] = format_date(date_raw)
    row["FlightNumber"] = code
    row["OriginAirport"] = airport(departure)
    row["DestinationAirport"] = airport(arrival)
    row["DestinationRaw"] = arrival
    row["Fare"] = fare
    row["UnmappedFields"] = json.dumps(unmapped, ensure_ascii=False) if unmapped else ""
    row["RawRecord"] = json.dumps(raw, ensure_ascii=False)
    return row


def convert(input_path=INPUT, output_path=OUTPUT):
    input_path, output_path = Path(input_path).resolve(), Path(output_path).resolve()
    if input_path == output_path:
        raise ValueError("Входной и выходной файлы должны отличаться")
    source = input_path.relative_to(BASE).as_posix() if BASE in input_path.parents else input_path.as_posix()
    temporary = output_path.with_suffix(".csv.tmp")
    count = 0
    try:
        tree = ET.parse(input_path)
        root = tree.getroot()
        if root.tag != "PointzAggregatorUsers":
            raise ValueError(f"Неожиданный корневой элемент: {root.tag!r}")

        with temporary.open("w", encoding="utf-8", newline="") as dst:
            writer = csv.DictWriter(dst, fieldnames=COLUMNS, lineterminator="\n")
            writer.writeheader()

            for user in root.findall("user"):
                uid = user.get("uid", "") or ""
                name = user.find("name")
                first = clean(name.get("first", "")) if name is not None else ""
                last = clean(name.get("last", "")) if name is not None else ""
                full = " ".join(part for part in (first, last) if part)

                for cards in user.findall("cards"):
                    cards_type = cards.get("type", "") or ""
                    for card in cards.findall("card"):
                        card_number = clean(card.get("number", ""))
                        program = clean(card.findtext("bonusprogramm"))
                        for activities in card.findall("activities"):
                            activities_type = activities.get("type", "") or ""
                            for index, activity in enumerate(activities.findall("activity"), 1):
                                record = f"user:{uid}/card:{card_number}/activity:{index}"
                                writer.writerow(build_row(
                                    activity=activity,
                                    uid=uid, first=first, last=last, full=full,
                                    cards_type=cards_type,
                                    card_number=card_number,
                                    program=program,
                                    activities_type=activities_type,
                                    record=record,
                                    source=source,
                                ))
                                count += 1
        temporary.replace(output_path)
    finally:
        temporary.unlink(missing_ok=True)
    return count


if __name__ == "__main__":
    print(f"Готово: {convert()} строк → {OUTPUT}")
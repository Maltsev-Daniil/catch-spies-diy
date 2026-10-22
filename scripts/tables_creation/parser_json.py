# очень много пустых столбцов, это надо обсудить

import json
import csv
from pathlib import Path

SOURCE_TYPE = "forum_json"
SOURCE_FILE = "data/FrequentFlyerForum-Profiles.json"

COLUMNS = [
    "SourceType", "SourceFile", "SourceSheet", "SourceRecord",
    "SourceEntityId", "UserId", "NickName", "PassengerTitle",
    "PassengerFullName", "PassengerFirstName", "PassengerSecondName",
    "PassengerLastName", "PassengerSex", "PassengerBirthDate",
    "PassengerDocument", "Passports", "BookingCode", "TicketNumber",
    "FrequentFlyer", "BonusProgramCode", "FrequentFlyerNumber",
    "BonusProgram", "FrequentFlyerStatus", "LoyaltyPrograms",
    "CardType", "ActivitiesType", "ActivityType", "FlightDate",
    "FlightTime", "ArrivalDate", "ArrivalTime", "FlightNumber",
    "CodeShare", "OriginCity", "OriginCountry", "OriginAirport",
    "DestinationCity", "DestinationCountry", "DestinationAirport",
    "DestinationRaw", "TravelClass", "Fare", "FlightStatus", "Gate",
    "Seat", "BoardingSequence", "Baggage", "Meal", "OperatorNote",
    "PaxAdditionalInfo", "AgentInfo", "UnmappedFields", "RawRecord"
]


def json_cell(value):
    return json.dumps(
        value, ensure_ascii=False, separators=(",", ":")
    )


def clean(value):
    if value is None:
        return None
    if isinstance(value, str):
        value = value.strip()
        return value if value else None
    return value

def clean_country(value):
    value = clean(value)
    if value is None:
        return None
    if value == "United States of":
        return "United States of America"
    if value == "United States":
        return "United States of America"
    return value

def clean_name(value):
    value = clean(value)
    if value is None:
        return None
    if not value or not isinstance(value, str):
        return value
    replacements = [
        ('YU', 'IU'), ('Yu', 'Iu'), ('yu', 'iu'),
        ('YA', 'IA'), ('Ya', 'Ia'), ('ya', 'ia'),
        ('YO', 'IO'), ('Yo', 'Io'), ('yo', 'io'),
        ('YE', 'IE'), ('Ye', 'Ie'), ('ye', 'ie'),
    ]
    result = value
    for old, new in replacements:
        result = result.replace(old, new)
    return result

def parse_json(input_path, output_dir="output"):
    print("Начало парсинга")
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    with open(input_path, encoding="utf-8") as f:
        data = json.load(f)

    profiles = data.get("Forum Profiles", [])
    print(f"Всего профилей: {len(profiles)}")
    if not isinstance(profiles, list):
        raise ValueError('"Forum Profiles" должен быть массивом')

    rows = []
    issues = []
    profiles_without_flights = []
    records_found = 0
    records_failed = 0

    known_profile = {
        "Registered Flights", "NickName", "Travel Documents",
        "Sex", "Loyality Programm", "Real Name"
    }
    known_flight = {
        "Date", "Codeshare", "Arrival", "Flight", "Departure"
    }

    for p_idx, profile in enumerate(profiles, start=1):
        entity_id = f"profile:{p_idx}"
        print(f'\t{entity_id}')

        if not isinstance(profile, dict):
            print("Warning: Профиль - не словарь")
            records_failed += 1
            issues.append({
                "SourceType": SOURCE_TYPE,
                "SourceFile": SOURCE_FILE,
                "SourceRecord": entity_id,
                "Field": "",
                "Issue": "Profile is not an object",
                "Action": "Profile skipped"
            })
            continue

        flights = profile.get("Registered Flights") or []

        real_name = profile.get("Real Name") or {}
        first_name = clean_name(real_name.get("First Name"))
        last_name = clean_name(real_name.get("Last Name"))

        full_name = " ".join(
            x for x in (first_name, last_name) if x
        ) or None

        # Keep only actual passport values; original profile is in RawRecord.
        documents = profile.get("Travel Documents") or []
        passports = [
            doc["Passports"]
            for doc in documents
            if isinstance(doc, dict)
            and doc.get("Passports") is not None
        ]
        passports_value = json_cell(passports) if passports else None

        loyalty = profile.get("Loyality Programm") or []
        loyalty_value = json_cell(loyalty) if loyalty else None

        if not flights:
            print("Warning: у профиля нет полетов")
            profiles_without_flights.append({
                "SourceType": SOURCE_TYPE,
                "SourceFile": SOURCE_FILE,
                "SourceEntityId": entity_id,
                "Profile": profile
            })

        for f_idx, flight in enumerate(flights, start=1):
            records_found += 1
            record_id = f"{entity_id}/flight:{f_idx}"
            print(f'\t\t{record_id}')

            if not isinstance(flight, dict):
                print('Warning: полет - не словарь')
                records_failed += 1
                issues.append({
                    "SourceType": SOURCE_TYPE,
                    "SourceFile": SOURCE_FILE,
                    "SourceRecord": record_id,
                    "Field": "",
                    "Issue": "Flight is not an object",
                    "Action": "Flight skipped"
                })
                continue

            row = dict.fromkeys(COLUMNS, None)

            row.update({
                "SourceType": SOURCE_TYPE,
                "SourceFile": SOURCE_FILE,
                "SourceRecord": record_id,
                "SourceEntityId": entity_id,
                "NickName": clean(profile.get("NickName")),
                "PassengerFullName": full_name,
                "PassengerFirstName": first_name,
                "PassengerLastName": last_name,
                "Passports": passports_value,
                "LoyaltyPrograms": loyalty_value,
            })

            # Normalize sex only when the source value is unambiguous.
            sex = clean(profile.get("Sex"))
            sex_map = {"Male": "M", "Female": "F", "X": "X"}
            row["PassengerSex"] = sex_map.get(sex)

            # Strict date validation; preserve the original in RawRecord.
            flight_date = clean(flight.get("Date"))
            if flight_date:
                try:
                    from datetime import date
                    date.fromisoformat(flight_date)
                    if len(flight_date) == 10:
                        row["FlightDate"] = flight_date
                    else:
                        raise ValueError
                except ValueError:
                    issues.append({
                        "SourceType": SOURCE_TYPE,
                        "SourceFile": SOURCE_FILE,
                        "SourceRecord": record_id,
                        "Field": "Date",
                        "Issue": "Invalid or non-ISO date",
                        "Action": "FlightDate left blank"
                    })

            codeshare = flight.get("Codeshare")
            if isinstance(codeshare, bool):
                row["CodeShare"] = str(codeshare).lower()
            elif codeshare is not None:
                print('Wanring: CodeShare не bool')
                issues.append({
                    "SourceType": SOURCE_TYPE,
                    "SourceFile": SOURCE_FILE,
                    "SourceRecord": record_id,
                    "Field": "Codeshare",
                    "Issue": "Value is not a boolean",
                    "Action": "CodeShare left blank"
                })

            row["FlightNumber"] = clean(flight.get("Flight"))

            departure = flight.get("Departure") or {}
            arrival = flight.get("Arrival") or {}

            row["OriginCity"] = clean(departure.get("City"))
            row["OriginCountry"] = clean_country(departure.get("Country"))
            row["OriginAirport"] = (
                clean(departure.get("Airport")).upper()
                if clean(departure.get("Airport")) else None
            )

            row["DestinationCity"] = clean(arrival.get("City"))
            row["DestinationCountry"] = clean_country(arrival.get("Country"))
            row["DestinationAirport"] = (
                clean(arrival.get("Airport")).upper()
                if clean(arrival.get("Airport")) else None
            )

            # Preserve unknown keys rather than silently discarding them.
            unknown_profile = {
                k: v for k, v in profile.items()
                if k not in known_profile
            }
            unknown_flight = {
                k: v for k, v in flight.items()
                if k not in known_flight
            }

            unmapped = {}
            if unknown_profile:
                unmapped["profile"] = unknown_profile
            if unknown_flight:
                unmapped["flight"] = unknown_flight

            if unmapped:
                row["UnmappedFields"] = json_cell(unmapped)

            # Include parent profile fields and this specific flight.
            # Do not duplicate the full flight list inside every row.
            raw_profile = {
                k: v for k, v in profile.items()
                if k != "Registered Flights"
            }
            row["RawRecord"] = json_cell({
                "profile": raw_profile,
                "flight": flight
            })

            rows.append(row)

    # Write CSV using the agreed column order and LF line endings.
    with open(
        output_dir / "forum_json.csv",
        "w", encoding="utf-8", newline=""
    ) as f:
        writer = csv.DictWriter(
            f, fieldnames=COLUMNS, lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(rows)

    with open(
        output_dir / "forum_profiles.jsonl",
        "w", encoding="utf-8", newline="\n"
    ) as f:
        for profile in profiles_without_flights:
            f.write(json_cell(profile) + "\n")

    issue_columns = [
        "SourceType", "SourceFile", "SourceRecord",
        "Field", "Issue", "Action"
    ]
    with open(
        output_dir / "forum_json_issues.csv",
        "w", encoding="utf-8", newline=""
    ) as f:
        writer = csv.DictWriter(
            f, fieldnames=issue_columns, lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(issues)

    report = {
        "ProfilesFound": len(profiles),
        "FlightRecordsFound": records_found,
        "RowsWritten": len(rows),
        "RecordsFailed": records_failed,
        "ProfilesWithoutFlights": len(profiles_without_flights),
        "IssuesLogged": len(issues)
    }

    with open(
        output_dir / "forum_json_report.json",
        "w", encoding="utf-8"
    ) as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parse_json("путь к файлу")
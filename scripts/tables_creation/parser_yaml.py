import csv
import json
from pathlib import Path

import yaml

SOURCE_TYPE = "skyteam_yaml"
SOURCE_FILE = "data/SkyTeam-Exchange.yaml"

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

ISSUE_COLUMNS = [
    "SourceType", "SourceFile", "SourceRecord",
    "Field", "Issue", "Action"
]


def json_cell(value):
    return json.dumps(
        value, ensure_ascii=False, separators=(",", ":"), default=str
    )


def clean(value):
    if value is None:
        return None
    if isinstance(value, str):
        value = value.strip()
        return value if value else None
    return value


def add_issue(issues, record_id, field, problem, action):
    issues.append({
        "SourceType": SOURCE_TYPE,
        "SourceFile": SOURCE_FILE,
        "SourceRecord": record_id,
        "Field": field,
        "Issue": problem,
        "Action": action
    })


def parse_yaml(input_path, output_dir="output_yaml"):
    print("Начало парсинга")

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    class UniqueKeyLoader(yaml.SafeLoader):
        pass

    def construct_mapping(loader, node, deep=False):
        result = {}
        for key_node, value_node in node.value:
            key = loader.construct_object(key_node, deep=deep)
            if key in result:
                raise ValueError(
                    f"Повторяющийся YAML-ключ {key!r}, "
                    f"строка {key_node.start_mark.line + 1}"
                )
            result[key] = loader.construct_object(value_node, deep=deep)
        return result

    UniqueKeyLoader.add_constructor(
        yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
        construct_mapping
    )

    print("Открываю файл:", input_path, flush=True)

    with open(input_path, encoding="utf-8") as f:
        print("Файл открыт. Загружаю YAML...", flush=True)
        data = yaml.load(f, Loader=UniqueKeyLoader)

    print("YAML загружен", flush=True)

    print(40 * '-')

    if not isinstance(data, dict):
        raise ValueError("Корень YAML должен быть словарём")

    rows = []
    issues = []
    flights_without_ff = []

    flights_found = 0
    records_found = 0
    records_failed = 0
    unknown_fields = set()

    known_flight = {"FF", "FROM", "TO", "STATUS"}
    known_participant = {"CLASS", "FARE"}

    print(f"Всего дат: {len(data)}")

    for flight_date, flights in data.items():
        if not isinstance(flights, dict):
            add_issue(
                issues, str(flight_date), "",
                "Date value is not a mapping",
                "Date group skipped"
            )
            records_failed += 1
            continue

        for flight_number, flight in flights.items():
            flights_found += 1
            flight_number = str(flight_number)

            flight_id = f"{flight_date}/{flight_number}"

            if not isinstance(flight, dict):
                add_issue(
                    issues, flight_id, "Flight",
                    "Flight is not an object", "Flight skipped"
                )
                records_failed += 1
                continue

            ff = flight.get("FF")

            if ff is None:
                participants = {}
            elif isinstance(ff, dict):
                participants = ff
            else:
                participants = {}
                add_issue(
                    issues, flight_id, "FF",
                    "FF is not a mapping",
                    "Flight saved to skyteam_flights.jsonl"
                )

            # Keep flights without participants separately.
            if not participants:
                flights_without_ff.append({
                    "SourceType": SOURCE_TYPE,
                    "SourceFile": SOURCE_FILE,
                    "SourceRecord": flight_id,
                    "FlightDate": str(flight_date),
                    "FlightNumber": flight_number,
                    "RawRecord": flight
                })

            unknown_flight = {
                k: v for k, v in flight.items()
                if k not in known_flight
            }

            for participant_key, participant in participants.items():
                records_found += 1
                participant_key = str(participant_key)
                record_id = f"{flight_id}/FF/{participant_key}"

                if not isinstance(participant, dict):
                    add_issue(
                        issues, record_id, "FF",
                        "Participant is not an object",
                        "Participant skipped"
                    )
                    records_failed += 1
                    continue

                # The source key is retained in full. Split only when
                # it clearly has the form "PROGRAM_CODE NUMBER".
                parts = participant_key.split()
                program_code = parts[0] if len(parts) == 2 else None
                program_number = parts[1] if len(parts) == 2 else None

                if program_code is None:
                    add_issue(
                        issues, record_id, "FF",
                        "Participant key has unexpected format",
                        "Program code and number left blank"
                    )

                unknown_participant = {
                    k: v for k, v in participant.items()
                    if k not in known_participant
                }

                unmapped = {}
                if unknown_flight:
                    unmapped["flight"] = unknown_flight
                if unknown_participant:
                    unmapped["participant"] = unknown_participant

                for key in unknown_flight:
                    unknown_fields.add(f"flight.{key}")
                for key in unknown_participant:
                    unknown_fields.add(f"participant.{key}")

                if unmapped:
                    add_issue(
                        issues, record_id, "UnmappedFields",
                        "Unknown fields: " + ", ".join(unmapped.keys()),
                        "Preserved in UnmappedFields and RawRecord"
                    )

                row = dict.fromkeys(COLUMNS, None)

                row.update({
                    "SourceType": SOURCE_TYPE,
                    "SourceFile": SOURCE_FILE,
                    "SourceRecord": record_id,
                    "FlightDate": str(flight_date),
                    "FlightNumber": flight_number,

                    # Explicit source mappings
                    "FrequentFlyer": participant_key,
                    "BonusProgramCode": program_code,
                    "FrequentFlyerNumber": program_number,
                    "OriginAirport": (
                        clean(flight.get("FROM")).upper()
                        if clean(flight.get("FROM")) else None
                    ),
                    "DestinationAirport": (
                        clean(flight.get("TO")).upper()
                        if clean(flight.get("TO")) else None
                    ),
                    "FlightStatus": clean(flight.get("STATUS")),
                    "TravelClass": clean(participant.get("CLASS")),
                    "Fare": clean(participant.get("FARE")),

                    "UnmappedFields": json_cell(unmapped) if unmapped else None,
                    "RawRecord": json_cell({
                        "date": flight_date,
                        "flight_number": flight_number,
                        "flight": flight,
                        "participant_key": participant_key,
                        "participant": participant
                    })
                })

                rows.append(row)

    # Main CSV
    with open(
        output_dir / "skyteam_yaml.csv",
        "w", encoding="utf-8", newline=""
    ) as f:
        writer = csv.DictWriter(
            f, fieldnames=COLUMNS, lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(rows)

    # Flights without participants
    with open(
        output_dir / "skyteam_flights.jsonl",
        "w", encoding="utf-8", newline=""
    ) as f:
        for flight in flights_without_ff:
            f.write(json_cell(flight) + "\n")

    # Issues
    with open(
        output_dir / "skyteam_yaml_issues.csv",
        "w", encoding="utf-8", newline=""
    ) as f:
        writer = csv.DictWriter(
            f, fieldnames=ISSUE_COLUMNS, lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(issues)

    report = {
        "FlightsFound": flights_found,
        "ParticipantRecordsFound": records_found,
        "RowsWritten": len(rows),
        "RecordsFailed": records_failed,
        "FlightsWithoutParticipants": len(flights_without_ff),
        "IssuesLogged": len(issues),
        "UnknownFields": sorted(unknown_fields)
    }

    with open(
        output_dir / "skyteam_yaml_report.json",
        "w", encoding="utf-8"
    ) as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parse_yaml("../Airlines-All/Airlines/SkyTeam-Exchange.yaml")

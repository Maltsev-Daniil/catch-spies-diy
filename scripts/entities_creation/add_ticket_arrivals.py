from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parent.parent
TICKETS = ROOT / "warehouse" / "bd_tables" / "tickets.csv"
SIRENA = ROOT / "lake" / "done_tables" / "sirena_tab.csv"
FLIGHT_KEY = ["FlightNumber", "FlightDate", "FlightTime"]
ARRIVAL = ["ArrivalTime", "ArrivalDate"]


def unique_arrivals(source, key):
    candidates = source.dropna(subset=key + ARRIVAL)[key + ARRIVAL].drop_duplicates()
    counts = candidates.groupby(key, dropna=False).size()
    return candidates.set_index(key).loc[counts[counts.eq(1)].index].reset_index()


def main():
    tickets = pd.read_csv(TICKETS, dtype="string")
    sirena = pd.read_csv(
        SIRENA, usecols=["TicketNumber"] + FLIGHT_KEY + ARRIVAL, dtype="string"
    )

    exact = unique_arrivals(sirena, ["TicketNumber"] + FLIGHT_KEY)
    by_flight = unique_arrivals(sirena, FLIGHT_KEY)

    tickets = tickets.drop(columns=ARRIVAL, errors="ignore")
    tickets = tickets.merge(exact, on=["TicketNumber"] + FLIGHT_KEY,
                            how="left", validate="many_to_one", sort=False)
    tickets = tickets.merge(by_flight, on=FLIGHT_KEY, how="left",
                            suffixes=("", "_flight"), validate="many_to_one", sort=False)
    for column in ARRIVAL:
        tickets[column] = tickets[column].fillna(tickets.pop(column + "_flight"))

    tickets.to_csv(TICKETS, index=False)
    print(f"Arrival fields filled: {tickets['ArrivalTime'].notna().sum()} / {len(tickets)}")


if __name__ == "__main__":
    main()

import pandas as pd
pd.set_option('display.max_columns', None)
pd.set_option('display.width', 200)

columns = ['PassengerFirstName', 'PassengerSecondName', 'PassengerLastName', 'PassengerDocument', 'TicketNumber', 'FlightDate', 'FlightNumber', 'FlightTime']
tmp_df = pd.DataFrame(columns=columns)

df_passengers = pd.read_csv('bd_tables/passangers.csv')
df_csv = pd.read_csv('../lake/done_tables/boarding_csv.csv')
df_xlsx = pd.read_csv('../lake/done_tables/boarding_xlsx.csv')
df_xlsx['PassengerDocument'] = df_xlsx['PassengerDocument'].astype('object')
df_tab = pd.read_csv('../lake/done_tables/sirena_tab.csv')

df_csv['TicketNumber'] = df_csv['TicketNumber'].replace('Not presented', pd.NA)

# добавляем пасспорт из passengers для пассажиров из xlsx
doc_dict = {}
for idx, row in df_passengers.iterrows():
    fname = str(row['PassengerFirstName']).strip()
    lname = str(row['PassengerLastName']).strip()
    doc = row['PassengerDocument']

    if (fname, lname) not in doc_dict:
        doc_dict[(fname, lname)] = doc

passport = 0
for idx, row in df_xlsx.iterrows():
    fname = str(row['PassengerFirstName']).strip()
    lname = str(row['PassengerLastName']).strip()

    if (fname, lname) in doc_dict:
        passport += 1
        df_xlsx.loc[idx, 'PassengerDocument'] = doc_dict[(fname, lname)]

df_xlsx_filtered = df_xlsx[df_xlsx['PassengerDocument'].notna()]
# добавляем в tmp_df строки из xlsx, где пасспорт не пустой
tmp_df = pd.concat([tmp_df, df_xlsx_filtered.reindex(columns=columns)], ignore_index=True)

# добавляем в tmp_df строки из tab
tmp_df = pd.concat([tmp_df, df_tab.reindex(columns=columns)], ignore_index=True)

df_csv_with_ticket = df_csv[df_csv['TicketNumber'].notna()]
tmp_df = pd.concat([tmp_df, df_csv_with_ticket.reindex(columns=columns)], ignore_index=True)

df_csv_no_ticket  = df_csv[df_csv['TicketNumber'].isna()]
flight_keys = ['PassengerDocument', 'FlightNumber', 'FlightDate', 'FlightTime']

# берем только нужные колонки из tmp_df
tmp_tickets = tmp_df[flight_keys + ['TicketNumber']].dropna(subset=['TicketNumber'])

tmp_tickets = tmp_tickets.drop_duplicates(subset=flight_keys, keep='first')

merged = df_csv_no_ticket.merge(
    tmp_tickets,
    on=flight_keys,
    how='left',
    suffixes=('', '_found')
)

merged['TicketNumber'] = merged['TicketNumber'].fillna(merged['TicketNumber_found'])

df_found = merged[merged['TicketNumber'].notna()]
tmp_df = pd.concat([tmp_df, df_found.reindex(columns=columns)], ignore_index=True)

not_found = merged[merged['TicketNumber'].isna()]

tmp_df = tmp_df.drop_duplicates()

# tmp_df = tmp_df.drop_duplicates(subset=['TicketNumber'], keep='first')

mask_na_ticket = tmp_df['TicketNumber'].isna()
if mask_na_ticket.any():
    df_na = tmp_df[mask_na_ticket].drop_duplicates(
        subset=['PassengerDocument', 'FlightNumber', 'FlightDate', 'FlightTime'],
        keep='first'
    )
    df_not_na = tmp_df[~mask_na_ticket]
    tmp_df = pd.concat([df_not_na, df_na], ignore_index=True)

tmp_df.to_csv('bd_tables/tickets.csv', index=False)

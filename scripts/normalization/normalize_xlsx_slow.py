import pandas as pd
df = pd.read_csv('done_tables/boarding_xlsx.csv')

first_names = set()
last_names = set()

for idx, row in df.iterrows():
    if pd.notna(row['PassengerFirstName']):
        first_names.add(row['PassengerFirstName'])
    if pd.notna(row['PassengerLastName']):
        last_names.add(row['PassengerLastName'])

print(f'{len(first_names)}, {len(last_names)}')

cnt = 0
for idx, row in df.iterrows():
    if idx % 10000 == 0:
        print(idx)
    if pd.notna(row['PassengerFirstName']):
        continue

    full_name = row['PassengerFullName']
    if pd.isna(full_name):
        continue
    parts = full_name.strip().split()

    if len(parts) == 2:
        if parts[0] in first_names:
            df.loc[idx, 'PassengerFirstName'] = parts[0]
            df.loc[idx, 'PassengerLastName'] = parts[1]
        elif parts[0] in last_names:
            df.loc[idx, 'PassengerFirstName'] = parts[1]
            df.loc[idx, 'PassengerLastName'] = parts[0]
        else:
            cnt += 1
print(cnt)
#==================================================================================
import json
import ast

def get_ticket_from_unmapped(unmapped_str):
    if pd.isna(unmapped_str):
        return None
    try:
        data = ast.literal_eval(unmapped_str)
        return str(data['E13']).strip()
    except (ValueError, SyntaxError, KeyError):
        return None

df['TicketNumber'] = df['UnmappedFields'].apply(get_ticket_from_unmapped)
df['TicketNumber'] = df['TicketNumber'].astype(str)
df['TicketNumber'] = df['TicketNumber'].replace('None', pd.NA)

df.to_csv('done_tables/new_boarding_xlsx.csv', index=False)

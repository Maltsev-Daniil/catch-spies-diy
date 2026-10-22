import pandas as pd
PATH = "/home/nitsir/Projects/DS/catch-spies/done_tables/"
df = pd.read_csv(PATH + "sirena_tab.csv")
df[['PassengerLastName', 'PassengerFirstName', 'PassengerSecondName']] = (
    df['PassengerFullName'].str.strip().str.split(r'\s+', expand=True)
)
df.to_csv(PATH + "sirena_tab_norm.csv", index=False)

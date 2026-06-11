import pandas as pd
import numpy as np

df = pd.read_csv(r"banking_data\transactions.csv")

accounts = set(df['account_id'])

accounts = pd.DataFrame(accounts, columns=['account_id'])

accounts.to_csv(r'banking_data\lookup_data\valid_accounts.csv', index=False)
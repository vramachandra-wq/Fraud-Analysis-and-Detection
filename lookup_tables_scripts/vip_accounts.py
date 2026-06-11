import pandas as pd
import numpy as np

blacklisted_accounts = pd.read_csv(r"banking_data\lookup_data\blacklisted_accounts.csv")
valid_accounts = pd.read_csv(r"banking_data\lookup_data\valid_accounts.csv")

blacklisted_accounts = set(blacklisted_accounts['account_id'])
valid_accounts = set(valid_accounts['account_id'])

accounts = list(valid_accounts - blacklisted_accounts)

np.random.seed(42)
selected_accounts = np.random.choice(accounts, size=100, replace=False)

amount_limits = np.random.choice(np.arange(100_000, 2_000_001, 100), size=100)
vip_accounts = pd.DataFrame({
    'account_id': selected_accounts,
    'per_transaction_amount_limit': amount_limits,
    'transaction_volume_limit_per_day': np.random.randint(3, 10, size=100)
})

print(vip_accounts.head())

vip_accounts.to_csv(r"banking_data\lookup_data\vip_accounts.csv", index=False)
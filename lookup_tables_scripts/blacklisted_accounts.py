import pandas as pd

# Read transactions
transactions = pd.read_csv(r'banking_data\transactions.csv')

# Get account_ids of fraudulent transactions
blacklisted_accounts_df = transactions.loc[transactions['is_fraud'] == 1,['account_id']].drop_duplicates()

# Save to CSV
blacklisted_accounts_df.to_csv(r'banking_data\lookup_data\blacklisted_accounts.csv',index=False)

print(f"Saved {len(blacklisted_accounts_df)} blacklisted accounts.")
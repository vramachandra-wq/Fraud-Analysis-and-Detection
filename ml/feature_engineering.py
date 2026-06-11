import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, TransformerMixin


class FraudFeatureEngineer(BaseEstimator, TransformerMixin):
    """Custom sklearn transformer that engineers fraud-detection features."""

    def fit(self, X, y=None):
        X = X.copy()
        X["transaction_date"] = pd.to_datetime(X["transaction_date"], errors="coerce")
        X["transaction_time"] = pd.to_datetime(X["transaction_time"], format="%H:%M:%S", errors="coerce")

        self.customer_avg_ = X.groupby("account_id")["amount"].mean().to_dict()
        self.customer_std_ = (X.groupby("account_id")["amount"].std().fillna(1).replace(0, 1).to_dict())
        self.device_count_ = X.groupby("device_id")["amount"].count().to_dict()
        self.location_count_ = X.groupby("location_id")["amount"].count().to_dict()

        daily_counts = (X.groupby(["account_id", "transaction_date"]).size().reset_index(name="count"))
        self.account_avg_daily_count_ = (daily_counts.groupby("account_id")["count"].mean().to_dict())
        daily_amounts = (X.groupby(["account_id", "transaction_date"])["amount"].sum().reset_index(name="daily_sum"))
        self.account_avg_daily_amount_ = (daily_amounts.groupby("account_id")["daily_sum"].mean().to_dict())

        self.global_customer_avg_ = X["amount"].mean()
        self.global_daily_count_ = daily_counts["count"].mean()
        self.global_daily_amount_ = daily_amounts["daily_sum"].mean()
        return self

    def transform(self, X):
        X = X.copy()
        X["transaction_date"] = pd.to_datetime(X["transaction_date"], errors="coerce")
        X["transaction_time"] = pd.to_datetime(X["transaction_time"], format="%H:%M:%S", errors="coerce")

        X["transaction_day"] = X["transaction_date"].dt.day
        X["transaction_month"] = X["transaction_date"].dt.month
        X["transaction_weekday"] = X["transaction_date"].dt.weekday
        X["transaction_hour"] = X["transaction_time"].dt.hour

        X["is_night_transaction"] = ((X["transaction_hour"] >= 23) | (X["transaction_hour"] <= 5)).astype(np.uint8)
        X["is_weekend"] = (X["transaction_weekday"] >= 5).astype(np.uint8)

        customer_avg = X["account_id"].map(self.customer_avg_).fillna(self.global_customer_avg_)
        customer_std = X["account_id"].map(self.customer_std_).fillna(1)
        customer_std = np.maximum(customer_std, 1)

        X["amount_vs_customer_avg"] = X["amount"] / (customer_avg + 1)
        X["customer_amount_zscore"] = (X["amount"] - customer_avg) / customer_std

        X["historical_avg_daily_count"] = X["account_id"].map(self.account_avg_daily_count_).fillna(self.global_daily_count_)
        X["historical_avg_daily_amount"] = X["account_id"].map(self.account_avg_daily_amount_).fillna(self.global_daily_amount_)
        X["device_transaction_count"] = X["device_id"].map(self.device_count_).fillna(0)
        X["location_transaction_count"] = X["location_id"].map(self.location_count_).fillna(0)

        X = X.drop(
            columns=[
                "account_id",
                "device_id",
                "location_id",
                "transaction_date",
                "transaction_time",
            ]
        )
        return X
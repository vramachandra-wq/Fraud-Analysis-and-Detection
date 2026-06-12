import pandas as pd
from ml.model_loader import load_pipeline

def run_ml_prediction(input_df: pd.DataFrame) -> tuple[float, int, str]:
    """
    Run the ML pipeline on a single-row DataFrame.

    Returns:
        fraud_probability (float), prediction (0/1), risk_category (str)
    """
    model = load_pipeline()
    raw_prob = model.predict_proba(input_df)[0][1]
    fraud_probability = float(getattr(raw_prob, "item", lambda: raw_prob)())

    prediction = 1 if fraud_probability >= 0.35 else 0

    if fraud_probability < 0.35:
        risk_cat = "NO_RISK"
    elif fraud_probability < 0.50:
        risk_cat = "LOW_RISK"
    elif fraud_probability < 0.75:
        risk_cat = "MEDIUM_RISK"
    else:
        risk_cat = "HIGH_RISK"

    return fraud_probability, prediction, risk_cat


def extract_engineered_features(input_df: pd.DataFrame) -> dict:
    """
    Run only the feature_engineer step of the pipeline and return the
    transformed row as a dict.
    """
    model = load_pipeline()
    try:
        engineered_df = model.named_steps["feature_engineer"].transform(input_df)
    except (AttributeError, KeyError):
        engineered_df = (model.transform(input_df) if hasattr(model, "transform") else input_df)
    return engineered_df.iloc[0].to_dict()

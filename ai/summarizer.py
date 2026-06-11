from ai.groq_client import get_groq_client
from config.settings import GROQ_SUMMARY_MODEL


def generate_transaction_summary(
    input_data: dict,
    features_dict: dict,
    prob: float,
    pred: int,
    risk: str,
    source: str,
    vip_context: dict | None = None,
) -> str:
    """
    Generate a natural-language AI summary for a transaction event.

    Handles BLACKLIST_RULE, VIP_PASS and ML_MODEL sources.
    Returns a plain-text paragraph.
    """
    if source == "BLACKLIST_RULE":
        return (
            f"The account {input_data.get('account_id', '')} is flagged for a "
            "fraudulent transaction and has been blocked."
        )

    client = get_groq_client()
    if not client:
        return "⚠️ Groq API key missing."

    status_str = "FRAUDULENT / HIGH RISK" if pred == 1 else "LEGITIMATE / SAFE"

    prompt = f"""
        You are a senior banking fraud analyst reviewing a transaction risk assessment.
        Your task is to write a short, specific summary paragraph (3-4 sentences) summarizing
        this activity based strictly on the metrics provided below.

        RAW TRANSACTION DETAILS:
        Account ID: {input_data['account_id']}
        Amount: {input_data['amount']}
        Merchant Category: {input_data['merchant_category']}
        Channel: {input_data['channel']}
        Date/Time: {input_data['transaction_date']} at {input_data['transaction_time']}
        Transaction Type: {input_data['transaction_type']}

        RISK ASSESSMENT:
        Final Decision: {status_str}
        Decision Source: {source}
    """

    if vip_context:
        count = vip_context["current_vol"]
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(
            count % 10 if not (11 <= count % 100 <= 13) else 0, "th"
        )
        count_str = f"{count}{suffix}"
        prompt += f"""
            VIP EXCEPTION CONTEXT:
            - Customer Tier: High-value customer
            - Allowable Transaction Limit: {vip_context['limit_amt']} {input_data['currency']}
            - Current Transaction Sequence Number: This is their {count_str} transaction for the day.
            - Remaining Transaction Capacity for the day: {vip_context['remaining_vol']}

            WRITING INSTRUCTIONS FOR VIP:
            Construct a natural narrative that explicitly matches this structural template format precisely:
            "This account belongs to a high value customer. The transaction value of {input_data['amount']} \
            {input_data['currency']} is within the allowable transaction limit for this customer, which is \
            {vip_context['limit_amt']} {input_data['currency']}. This is their {count_str} transaction for the day, \
            and they have {vip_context['remaining_vol']} transactions left for the day."
        """
    else:
        prompt += f"""
        WRITING INSTRUCTIONS FOR STANDARD TRACK:
        - Do NOT include or name any mathematical formulas, deviations, multipliers, ratios, or specific
          custom data pipeline features.
        - If {status_str} is FRAUDULENT: Focus entirely on uncharacteristic spending behavior, an anomalous
          target merchant type, suspicious velocity, or environment/timing factors that look out-of-pattern
          compared to expected client histories. Use cautious, investigative language.
        - If {status_str} is LEGITIMATE: Explain that the transaction appears entirely consistent with typical
          day-to-day spending behaviors and contains no notable environmental indicators of risk.
        """

    prompt += """
        GENERAL CRITERIA:
        - Do NOT mention: "XGBoost", "Machine learning", "Model features", "Feature names",
          "Importance scores", "Z-score", "Ratio", "Multiplier", or specific probability percentages.
        - Return ONLY the final clear paragraph text summary without any introductory tags.
    """

    try:
        completion = client.chat.completions.create(
            model=GROQ_SUMMARY_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a precise financial fraud investigator who summarizes "
                        "transaction entries using natural, narrative-driven text."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
            max_tokens=200,
        )
        return completion.choices[0].message.content.strip()
    except Exception as e:
        return f"Could not retrieve AI summary: {e}"

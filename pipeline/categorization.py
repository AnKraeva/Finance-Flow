import pandas as pd

from .utils import normalize_text

def match_rule(row: pd.Series, rule: dict) -> bool:
    cond = rule["conditions"]

    description = normalize_text(row.get("raw_description"))
    amount = row.get("raw_amount")
    source = row.get("source")
    tx_type = row.get("type")
    category = normalize_text(row.get("raw_category"))
    date = row.get("date")

    # --- description_contains ---
    if "description_contains" in cond:
        if not any(keyword in description for keyword in cond["description_contains"]):
            return False

    # --- amount_min ---
    if "amount_min" in cond:
        if amount is None or amount < cond["amount_min"]:
            return False

    # --- amount_max ---
    if "amount_max" in cond:
        if amount is None or amount > cond["amount_max"]:
            return False

    # --- source ---
    if "source" in cond:
        if source not in cond["source"]:
            return False

    # --- type ---
    if "type" in cond:
        if tx_type not in cond["type"]:
            return False

    # --- day_of_month_min ---
    if "day_of_month_min" in cond:
        if row["date"].day < cond["day_of_month_min"]:
            return False

    # --- day_of_month_max ---
    if "day_of_month_max" in cond:
        if row["date"].day > cond["day_of_month_max"]:
            return False

    # --- category ---
    if "category" in cond:
        if category not in [c.lower() for c in cond["category"]]:
            return False

    # --- weekday ---
    if "weekday" in cond:
        if pd.isna(date):
            return False
        if pd.to_datetime(date).weekday() not in cond["weekday"]:
            return False

    return True


def normalize_category_with_debug(row: pd.Series, rules: list) -> str:
    sorted_rules = sorted(rules, key=lambda x: x.get("priority", 100))

    for rule in sorted_rules:
        if match_rule(row, rule):
            return rule["new_category"], rule["name"]

    return row.get("category"), None


def assign_categories(df, rules):
    result = df.apply(
        lambda row: normalize_category_with_debug(row, rules),
        axis=1
    )

    return df.assign(
        category=result.str[0],
        subcategory=result.str[1]
    )
import pandas as pd
import re

from .utils import normalize_text

# --- ТИП ОПЕРАЦИИ ---

def detect_type(row: pd.Series, config: dict) -> str:
    source = row.get("source")

    description = normalize_text(row.get("raw_description"))
    category = normalize_text(row.get("raw_category"))
    direction = str(row.get("direction", "")).strip()

    # --- 1. SBER DEPOSIT / ACCOUNT ---
    if source in config["account_like"]:

        # чистим категорию от пунктуации
        category_clean = re.sub(r"[^\w\s]", "", category)

        # income
        if any(cat in category_clean for cat in config["income_categories"]):
            return "доход"

        # expense
        if any(acc in description for acc in config["external_accounts"]):
            return "расход"

        # остальное
        return "внутренний"

    # --- 2. SBER CARD / TBANK ---
    elif source in config["card_like"]:

        # internal
        if any(keyword in description for keyword in config["internal_keywords"]):
            return "внутренний"

        # income / expense
        if direction == "+":
            return "доход"
        elif direction == "-":
            return "расход"

        return "unknown"

    return "unknown"


def assign_types(df, rules):
    return df.assign(
        type=df.apply(lambda row: detect_type(row, rules), axis=1)
    )

# --- ВОЗВРАТЫ ---

def detect_refund(row: pd.Series, config: dict) -> str:

    description = normalize_text(row.get("raw_description"))
    category = normalize_text(row.get("category"))
    direction = str(row.get("direction", "")).strip()
    current_type = row.get("type")

    # --- исключаем internal ---
    if current_type == "внутренний":
        return current_type

    # --- определяем, что это поступление ---
    is_income = (direction == "+") or (current_type == "доход")

    if not is_income:
        return current_type

    # --- 1. явный возврат ---
    refund_keywords = [normalize_text(k) for k in config.get("refund_keywords", [])]

    if any(keyword in description for keyword in refund_keywords):
        return "возврат"

    # --- 2. неявный возврат по категории ---
    excluded_categories = [normalize_text(c) for c in config["refund_exclude_categories"]]

    if not any(excluded in category for excluded in excluded_categories):
        return "возврат"

    return current_type


def assign_refunds(df, config):
    return df.assign(
        type=df.apply(lambda row: detect_refund(row, config), axis=1)
    )
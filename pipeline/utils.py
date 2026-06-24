import pandas as pd
import re
import yaml


def normalize_text(text):
    if pd.isna(text):
        return ""
    text = str(text).lower()
    text = text.replace("\xa0", " ")  # важно для PDF
    text = re.sub(r"[^\w\s]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def load_yaml(path: str):
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)
"""Парсер выписки Т-Банка (CSV).

Формат: разделитель ';', десятичная запятая, дата операции с временем. Пример
строки (заголовки в первой строке файла):

    "Дата операции";...;"Статус";"Сумма операции";...;"Категория";"Описание";...
    "31.03.2026 19:19:44";...;"OK";"-359,00";...;"Супермаркеты";"Пятёрочка";...
"""
import pandas as pd

from .utils import split_amount_series

CSV_SEP = ";"
STATUS_OK = "OK"                       # берём только успешные операции
DATE_FORMAT = "%d.%m.%Y %H:%M:%S"

# Имена колонок CSV → канонические имена.
COLUMN_MAPPING = {
    "Дата операции": "date",
    "Категория": "raw_category",
    "Сумма операции": "raw_amount",
    "Описание": "raw_description",
}


def parse_tbank_csv(file_path: str) -> pd.DataFrame:
    df = (
        pd.read_csv(file_path, sep=CSV_SEP, engine="python", on_bad_lines="warn")
        .query("Статус == @STATUS_OK")
    )

    df = df.rename(columns=COLUMN_MAPPING)[list(COLUMN_MAPPING.values())]

    df["source"] = "tbank"
    df["date"] = pd.to_datetime(df["date"], format=DATE_FORMAT).dt.normalize()
    df["direction"], df["raw_amount"] = split_amount_series(df["raw_amount"])

    return df

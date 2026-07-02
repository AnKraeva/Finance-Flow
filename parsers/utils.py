"""Общие инструменты для парсеров: регулярки, разбор сумм/дат, нормализация
текста, обход PDF и валидация канонической схемы.

Этот модуль — нижний слой: он ничего не импортирует из ``pipeline`` (зависимость
идёт только в обратную сторону, ``pipeline`` → ``parsers``).
"""
from __future__ import annotations

import re
from typing import Iterator

import pandas as pd
import pdfplumber

# =========================================================
# КАНОНИЧЕСКАЯ СХЕМА
# =========================================================

# Ровно эти колонки должен вернуть каждый парсер (см. validate_schema).
CANONICAL_COLUMNS = [
    "source",
    "date",
    "direction",
    "raw_amount",
    "raw_category",
    "raw_description",
]

# =========================================================
# БАЗОВЫЕ ПАТТЕРНЫ
# =========================================================

DATE_PATTERN = r"\d{2}\.\d{2}\.\d{4}"
TIME_PATTERN = r"\d{2}:\d{2}(:\d{2})?"

DATETIME_PATTERN = rf"{DATE_PATTERN}\s+{TIME_PATTERN}"

MONEY_PATTERN = r"[+\-−]?\d[\d\s]*,\d{2}"
SIGNED_MONEY_PATTERN = r"[+\-]\s?\d[\d\s]*,\d{2}"

# =========================================================
# СКОМПИЛИРОВАННЫЕ (быстрее)
# =========================================================

RE_DATE = re.compile(DATE_PATTERN)
RE_DATETIME = re.compile(DATETIME_PATTERN)
RE_MONEY = re.compile(MONEY_PATTERN)
RE_SIGNED_MONEY = re.compile(SIGNED_MONEY_PATTERN)

RE_OZON_AMOUNT = re.compile(r"([+-])\s?(\d[\d\s]*[.,]\d{2})\s?₽")

# =========================================================
# ЧАСТЫЕ ШАБЛОНЫ
# =========================================================

RE_CARD_MASK = re.compile(r"\*{4}\d+")
RE_LONG_NUMBER = re.compile(r"\b\d{6,}\b")   # коды авторизации
RE_SPACES = re.compile(r"\s+")

RE_DATE_AT_START = re.compile(rf"^{DATE_PATTERN}\s+")

# Хвостовая сумма в строке — это остаток по счёту, его отбрасываем.
RE_TRAILING_BALANCE = re.compile(r"\d[\d\s]*,\d{2}$")


# =========================================================
# РАЗБОР СУММ / ТЕКСТА
# =========================================================

def parse_amount(raw: str) -> tuple[str, float]:
    """'+1 234,56' → ('+', 1234.56). Знак возвращается отдельно от модуля суммы.

    Убирает пробелы-разделители разрядов и нормализует минус (U+2212 → '-').
    Всё, что не начинается с '+', считается расходом ('-').
    """
    raw = raw.replace(" ", "").replace("−", "-")
    direction = "+" if raw.startswith("+") else "-"
    amount = float(raw.lstrip("+-").replace(",", "."))
    return direction, round(amount, 2)


def split_amount_series(raw: pd.Series) -> tuple[pd.Series, pd.Series]:
    """Векторный аналог parse_amount для колонки сумм (например, из CSV Т-Банка).

    Возвращает (direction, amount): direction ∈ {'+','-'}, amount — модуль float.
    """
    s = raw.astype(str)
    direction = s.str.contains("-", regex=False).map({True: "-", False: "+"})
    amount = (
        s.str.replace(" ", "", regex=False)
        .str.replace("−", "-", regex=False)
        .str.replace(",", ".", regex=False)
        .str.replace("-", "", regex=False)
        .astype(float)
        .round(2)
    )
    return direction, amount


def extract_digits(text: str) -> str:
    """Оставляет из строки только цифры (для номеров счетов/карт)."""
    return re.sub(r"\D", "", text)


def normalize_text(text) -> str:
    """Нормализует текст для сравнения с ключевыми словами правил.

    Нижний регистр; неразрывные пробелы из PDF (\\xa0) → обычные; пунктуация →
    пробелы; схлопывание пробелов. Применяется к обеим сторонам сравнения, поэтому
    ключевые слова в YAML пишут простым нижним регистром.
    """
    if pd.isna(text):
        return ""
    text = str(text).lower()
    text = text.replace("\xa0", " ")  # важно для PDF
    text = re.sub(r"[^\w\s]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


# =========================================================
# ОБХОД PDF
# =========================================================

def iter_pdf_pages(pdf_path: str) -> Iterator[list[str]]:
    """Отдаёт список строк каждой непустой страницы PDF.

    Инкапсулирует общий boilerplate парсеров Сбера (открыть PDF, пройтись по
    страницам, extract_text, пропустить пустые). Границы страниц сохраняются —
    посблочная логика вызывающего кода работает в пределах одной страницы.
    """
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if not text:
                continue
            yield text.splitlines()


# =========================================================
# ВАЛИДАЦИЯ СХЕМЫ
# =========================================================

def validate_schema(df: pd.DataFrame, source_hint: str = "") -> pd.DataFrame:
    """Проверяет, что парсер вернул ровно каноническую схему.

    Бросает ValueError при нарушении (ловится per-file в parse_folder, чтобы
    кривой парсер падал на границе, а не глубже в пайплайне). Пустой DataFrame
    (0 строк) допустим — файл мог не содержать операций.
    """
    prefix = f"[{source_hint}] " if source_hint else ""

    if df.empty:
        return df

    actual = set(df.columns)
    expected = set(CANONICAL_COLUMNS)
    if actual != expected:
        missing = expected - actual
        extra = actual - expected
        raise ValueError(
            f"{prefix}схема не совпадает: отсутствуют {sorted(missing)}, "
            f"лишние {sorted(extra)}"
        )

    if not df["direction"].isin(["+", "-"]).all():
        bad = sorted(set(df["direction"]) - {"+", "-"})
        raise ValueError(f"{prefix}direction содержит недопустимые значения: {bad}")

    if not pd.api.types.is_numeric_dtype(df["raw_amount"]):
        raise ValueError(f"{prefix}raw_amount должен быть числом, а не {df['raw_amount'].dtype}")

    if df["raw_amount"].isna().any() or (df["raw_amount"] < 0).any():
        raise ValueError(f"{prefix}raw_amount содержит NaN или отрицательные значения")

    if not pd.api.types.is_datetime64_any_dtype(df["date"]):
        raise ValueError(f"{prefix}date должен быть datetime, а не {df['date'].dtype}")

    return df

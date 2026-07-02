"""Парсер выписок Сбербанка (PDF).

Точка входа parse_sber_pdf по тексту первой страницы выбирает один из трёх
разборов — карта / счёт / вклад. Их макеты устроены по-разному:
  - карта: многострочные блоки, начинающиеся со строки «дата+время»;
  - счёт: одна операция = строка «дата ... сумма» + следующая строка с номером;
  - вклад: блок от строки с датой до строки, начинающейся с «к/с».
"""
from __future__ import annotations

import re

import pandas as pd
import pdfplumber

from .utils import (
    RE_DATE,
    RE_DATETIME,
    RE_MONEY,
    RE_SPACES,
    RE_CARD_MASK,
    RE_LONG_NUMBER,
    RE_DATE_AT_START,
    RE_TRAILING_BALANCE,
    parse_amount,
    extract_digits,
    iter_pdf_pages,
)

# --- специфичные для Сбера паттерны/маркеры ---
RE_SBER_CARD_OP = re.compile(r"Операция по карте.*")   # служебный хвост строки карты
CS_MARKER = "к/с"                                       # конец блока операции вклада
# Хвост операции вклада: "... 12, №" / "... -12, №" / "... №" — режем по нему.
RE_DEPOSIT_TAIL = re.compile(r"\s-?\d{2},\s№|\s\d{2},\s№|\s№")


def parse_sber_pdf(pdf_path: str) -> pd.DataFrame:
    with pdfplumber.open(pdf_path) as pdf:
        first_page_text = pdf.pages[0].extract_text()

    sber_types = {
        "дебетовой карты": parse_sber_card,
        "Сберегательный счет": parse_sber_account,
        "Накопительный счёт": parse_sber_account,
        "СберВклад": parse_sber_deposit,
    }

    for key, parser in sber_types.items():
        if key in first_page_text:
            return parser(pdf_path)

    raise ValueError("Неизвестный тип выписки Сбера")


# =========================================================
# ОБЩИЕ ХЕЛПЕРЫ ОЧИСТКИ
# =========================================================

def clean_text(text: str) -> str:
    """Убирает служебный хвост, маску карты и коды авторизации, схлопывает пробелы."""
    text = RE_SBER_CARD_OP.sub("", text)
    text = RE_CARD_MASK.sub("", text)
    text = RE_LONG_NUMBER.sub("", text)
    return RE_SPACES.sub(" ", text).strip()


def clean_category(text: str) -> str:
    """Отбрасывает ведущие числовые токены (коды) из строки категории."""
    parts = text.strip().split()
    while parts and parts[0].isdigit():
        parts.pop(0)
    return " ".join(parts)


def clean_description(text: str) -> str:
    """Снимает дату в начале строки и прогоняет общую очистку."""
    text = RE_DATE_AT_START.sub("", text)
    return clean_text(text)


def clean_operation_part(text: str) -> str:
    """Отрезает хвост операции вклада (номер документа) и обрезает пробелы."""
    return RE_DEPOSIT_TAIL.split(text)[0].strip()


def pick_operation_amount(amounts: list[str]) -> str:
    """В строке карты идут «сумма операции ... остаток»: сумма операции —
    предпоследнее число. Если число одно — оно и есть сумма."""
    return amounts[-2] if len(amounts) > 1 else amounts[0]


# =========================================================
# СБЕР — КАРТА
# =========================================================

def parse_sber_card(pdf_path: str) -> pd.DataFrame:
    rows: list[dict] = []

    for lines in iter_pdf_pages(pdf_path):
        i = 0
        while i < len(lines):
            line = lines[i]

            # --- начало операции: строка «дата+время» ---
            if not RE_DATETIME.match(line):
                i += 1
                continue

            # --- собираем блок до следующей строки «дата+время» ---
            block_lines = [line]
            j = i + 1
            while j < len(lines) and not RE_DATETIME.match(lines[j]):
                block_lines.append(lines[j])
                j += 1

            block_text = " ".join(block_lines)

            # --- дата ---
            date_match = RE_DATE.match(line)
            if not date_match:
                i = j
                continue
            date = pd.to_datetime(date_match.group(), dayfirst=True)

            # --- сумма ---
            amounts = RE_MONEY.findall(block_text)
            if not amounts:
                i = j
                continue
            direction, amount = parse_amount(pick_operation_amount(amounts))

            # --- категория (из первой строки блока) ---
            line_clean = RE_MONEY.sub("", line)
            line_clean = RE_DATETIME.sub("", line_clean)
            line_clean = RE_TRAILING_BALANCE.sub("", line_clean)
            raw_category = clean_category(line_clean)

            # --- описание (остальные строки блока) ---
            raw_description = clean_description(" ".join(block_lines[1:]))

            rows.append({
                "source": "sber_card",
                "date": date,
                "direction": direction,
                "raw_amount": amount,
                "raw_category": raw_category,
                "raw_description": raw_description,
            })

            i = j

    return pd.DataFrame(rows)


# =========================================================
# СБЕР — СЧЁТ
# =========================================================

def parse_sber_account(pdf_path: str) -> pd.DataFrame:
    rows: list[dict] = []

    for lines in iter_pdf_pages(pdf_path):
        i = 0
        while i < len(lines) - 1:
            line = lines[i]

            # --- дата в начале строки ---
            if not RE_DATE.match(line):
                i += 1
                continue

            next_line = lines[i + 1]

            # --- сумма ---
            amounts = RE_MONEY.findall(line)
            if not amounts:
                i += 1
                continue
            direction, amount = parse_amount(amounts[0])

            parts = line.split()

            rows.append({
                "source": "sber_account",
                "date": pd.to_datetime(parts[0], dayfirst=True),
                "direction": direction,
                "raw_amount": amount,
                "raw_category": parts[1],
                "raw_description": extract_digits(next_line),
            })

            i += 2

    return pd.DataFrame(rows)


# =========================================================
# СБЕР — ВКЛАД
# =========================================================

def parse_sber_deposit(pdf_path: str) -> pd.DataFrame:
    rows: list[dict] = []

    for lines in iter_pdf_pages(pdf_path):
        i = 0
        while i < len(lines):
            line = lines[i]

            # --- дата ---
            if not RE_DATE.match(line):
                i += 1
                continue
            date = pd.to_datetime(RE_DATE.match(line).group(), dayfirst=True)

            # --- сумма ---
            amounts = RE_MONEY.findall(line)
            if not amounts:
                i += 1
                continue
            direction, amount = parse_amount(amounts[0])

            # --- первая строка операции (без даты/суммы/остатка/хвоста) ---
            first_line = RE_DATE.sub("", line)
            first_line = RE_MONEY.sub("", first_line)
            first_line = RE_TRAILING_BALANCE.sub("", first_line)
            first_line = clean_operation_part(first_line)

            operation_lines = [first_line]

            # --- добираем строки до маркера «к/с» ---
            j = i + 1
            while j < len(lines) and not lines[j].strip().startswith(CS_MARKER):
                operation_lines.append(clean_operation_part(lines[j]).strip())
                j += 1

            category = RE_SPACES.sub(" ", " ".join(operation_lines)).strip()

            # --- описание: номер корр. счёта из строки «к/с» ---
            description = ""
            if j < len(lines) and lines[j].strip().startswith(CS_MARKER):
                description = extract_digits(lines[j])
                j += 1

            rows.append({
                "source": "sber_deposit",
                "date": date,
                "direction": direction,
                "raw_amount": amount,
                "raw_category": category,
                "raw_description": description,
            })

            i = j

    return pd.DataFrame(rows)

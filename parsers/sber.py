import pandas as pd
import re
import pdfplumber
from .utils import (
    RE_DATE,
    RE_DATETIME,
    RE_MONEY,
    RE_SPACES,
    RE_CARD_MASK,
    RE_LONG_NUMBER,
    RE_DATE_AT_START,
    parse_amount,
    extract_digits,
)


def parse_sber_pdf(pdf_path: str) -> pd.DataFrame:

    with pdfplumber.open(pdf_path) as pdf:
        first_page_text = pdf.pages[0].extract_text()

    SBER_TYPES = {
        "дебетовой карты": parse_sber_card,
        "Сберегательный счет": parse_sber_account,
        "Накопительный счёт": parse_sber_account,
        "СберВклад": parse_sber_deposit,
    }

    for key, parser in SBER_TYPES.items():
        if key in first_page_text:
            return parser(pdf_path)

    raise ValueError("Неизвестный тип выписки Сбера")

# =========================================================
# СБЕР — КАРТА
# =========================================================

def parse_sber_card(pdf_path: str) -> pd.DataFrame:
    rows = []

    def clean_text(text: str) -> str:
        text = re.sub(r"Операция по карте.*", "", text)   # специфичное — оставляем
        text = RE_CARD_MASK.sub("", text)
        text = RE_LONG_NUMBER.sub("", text)
        return RE_SPACES.sub(" ", text).strip()

    def clean_category(text: str) -> str:
        text = text.strip()
        parts = text.split()

        while parts and parts[0].isdigit():
            parts.pop(0)

        return " ".join(parts)

    def clean_description(text: str) -> str:
        text = RE_DATE_AT_START.sub("", text)
        return clean_text(text)

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if not text:
                continue

            lines = text.splitlines()

            i = 0
            while i < len(lines):

                line = lines[i]

                # --- начало операции ---
                if not RE_DATETIME.match(line):
                    i += 1
                    continue

                # --- собираем блок ---
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

                raw_amount = amounts[-2] if len(amounts) > 1 else amounts[0]
                direction, amount = parse_amount(raw_amount)

                # --- category ---
                line_clean = RE_MONEY.sub("", line)
                line_clean = RE_DATETIME.sub("", line_clean)
                line_clean = re.sub(r"\d[\d\s]*,\d{2}$", "", line_clean)  # остаток оставляем как есть

                raw_category = clean_category(line_clean)

                # --- description ---
                description_lines = block_lines[1:]
                raw_description = clean_description(" ".join(description_lines))

                rows.append({
                    "source": "sber_card",
                    "date": date,
                    "direction": direction,
                    "raw_amount": amount,
                    "raw_category": raw_category,
                    "raw_description": raw_description
                })

                i = j

    return pd.DataFrame(rows)


# =========================================================
# СБЕР — СЧЁТ
# =========================================================

def parse_sber_account(pdf_path: str) -> pd.DataFrame:
    rows = []

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if not text:
                continue

            lines = text.splitlines()

            i = 0
            while i < len(lines) - 1:
                line = lines[i]

                # --- дата ---
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
                    "raw_description": extract_digits(next_line)
                })

                i += 2

    return pd.DataFrame(rows)


# =========================================================
# СБЕР — ВКЛАД
# =========================================================

def parse_sber_deposit(pdf_path: str) -> pd.DataFrame:
    rows = []

    def clean_operation_part(text: str) -> str:
        text = re.split(r"\s-?\d{2},\s№|\s\d{2},\s№|\s№", text)[0]
        return text.strip()

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if not text:
                continue

            lines = text.splitlines()

            i = 0
            while i < len(lines):

                line = lines[i]

                # --- дата ---
                if not RE_DATE.match(line):
                    i += 1
                    continue

                date_match = RE_DATE.match(line)
                date = pd.to_datetime(date_match.group(), dayfirst=True)

                # --- сумма ---
                amounts = RE_MONEY.findall(line)
                if not amounts:
                    i += 1
                    continue

                direction, amount = parse_amount(amounts[0])

                # --- первая строка ---
                first_line = RE_DATE.sub("", line)
                first_line = RE_MONEY.sub("", first_line)
                first_line = re.sub(r"\d[\d\s]*,\d{2}$", "", first_line)
                first_line = clean_operation_part(first_line)

                operation_lines = [first_line]

                j = i + 1

                # --- собираем до "к/с" ---
                while j < len(lines) and not lines[j].strip().startswith("к/с"):
                    clean_line = clean_operation_part(lines[j])
                    operation_lines.append(clean_line.strip())
                    j += 1

                category = RE_SPACES.sub(" ", " ".join(operation_lines)).strip()

                # --- описание ---
                description = ""
                if j < len(lines) and lines[j].strip().startswith("к/с"):
                    description = extract_digits(lines[j])
                    j += 1

                rows.append({
                    "source": "sber_deposit",
                    "date": date,
                    "direction": direction,
                    "raw_amount": amount,
                    "raw_category": category,
                    "raw_description": description
                })

                i = j

    return pd.DataFrame(rows)
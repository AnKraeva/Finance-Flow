import re

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


def parse_amount(raw: str):
    raw = raw.replace(" ", "").replace("−", "-")
    direction = "+" if raw.startswith("+") else "-"
    amount = float(raw.lstrip("+-").replace(",", "."))
    return direction, round(amount, 2)


def extract_digits(text: str) -> str:
    return re.sub(r"\D", "", text)
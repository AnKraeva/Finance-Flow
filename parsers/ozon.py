"""Парсер выписки Ozon-кошелька (PDF).

Ozon не даёт текстовой таблицы — строки операций разделены тонкими
горизонтальными линиями/прямоугольниками. Парсер восстанавливает строки
геометрически: находит горизонтальные разделители и режет страницу на полосы
между ними, затем разбирает текст каждой полосы.
"""
from __future__ import annotations

import re
from typing import Callable

import pandas as pd
import pdfplumber

from .utils import RE_DATE, RE_SPACES, RE_OZON_AMOUNT, normalize_text, parse_amount

# --- пороги геометрии таблицы (эмпирика под макет Ozon) ---
H_LINE_MAX_HEIGHT = 2        # прямоугольник/линия тоньше этого считается горизонтальной
MIN_LINE_WIDTH_RATIO = 0.3   # разделитель должен покрывать ≥30% ширины страницы
MIN_ROW_HEIGHT = 10          # полосы тоньше этого — не строки операций, пропускаем

# Имя отправителя в СБП-переводе: "Иванов Иван И."
RE_OZON_SENDER = re.compile(r"Отправитель:\s*([А-ЯЁ][а-яё]+ [А-ЯЁ][а-яё]+ [А-ЯЁ]\.)")

DEFAULT_DESCRIPTION = "Ozon"
RAW_CATEGORY = "Маркетплейсы"


def _sbp_description(text_raw: str) -> str:
    """СБП-перевод: подставляем имя отправителя, если распозналось."""
    m = RE_OZON_SENDER.search(text_raw)
    sender = m.group(1) if m else ""
    return f"Ozon. СБП перевод от {sender}".strip()


# Правила описания проверяются по порядку, первое совпадение выигрывает.
# predicate(text_clean) -> bool; builder(text_raw) -> итоговое описание.
OZON_DESCRIPTION_RULES: list[tuple[Callable[[str], bool], Callable[[str], str]]] = [
    (lambda t: "возврат" in t, lambda _: "Ozon. Возврат"),
    (lambda t: "чаев" in t, lambda _: "Ozon. Чаевые"),
    (lambda t: "сбп" in t and "отправитель" in t, _sbp_description),
    (lambda t: "остатка эдс" in t, lambda _: "Ozon. Перевод остатка между счетами"),
    (lambda t: "зачисление средств с использованием карты" in t,
     lambda _: "Ozon. Зачисление с карты"),
    (lambda t: "оплата товаров" in t, lambda _: "Ozon. Оплата"),
]


def _extract_ozon_rows(pdf_path: str) -> list[str]:
    """Режет PDF по горизонтальным разделителям и возвращает текст строк таблицы."""
    payments: list[str] = []

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:

            # Ozon сменил отрисовку таблицы: в старых выписках строки разделялись
            # прямоугольниками (page.rects), в новых — линиями (page.lines).
            # Берём оба источника, чтобы парсер читал оба формата.
            rects = page.rects + page.lines

            # --- 1. горизонтальные линии ---
            h_rects = [r for r in rects if r["height"] < H_LINE_MAX_HEIGHT]
            if not h_rects:
                continue

            df_rects = pd.DataFrame(h_rects)
            df_rects["top_round"] = df_rects["top"].round(1)

            line_positions = (
                df_rects.groupby("top_round").agg({"width": "sum"}).reset_index()
            )
            line_positions = line_positions[
                line_positions["width"] > page.width * MIN_LINE_WIDTH_RATIO
            ]
            if len(line_positions) < 2:
                continue

            tops = line_positions.sort_values("top_round")["top_round"].tolist()

            # --- 2. режем на строки ---
            for top, bottom in zip(tops, tops[1:]):
                if bottom - top < MIN_ROW_HEIGHT:
                    continue

                bbox = (0, top, page.width, bottom)
                text = page.within_bbox(bbox).extract_text()
                if text and text.strip():
                    payments.append(RE_SPACES.sub(" ", text.strip()))

    return payments


def parse_ozon_row(text: str) -> pd.Series:
    """Разбирает одну строку таблицы Ozon в каноническую запись."""
    # --- amount + direction ---
    amount_match = RE_OZON_AMOUNT.search(text)
    if amount_match:
        direction, amount = parse_amount(amount_match.group(1) + amount_match.group(2))
    else:
        direction, amount = None, None

    # --- date ---
    date_match = RE_DATE.search(text)
    date = pd.to_datetime(date_match.group(), dayfirst=True) if date_match else None

    # --- description (data-driven, первое совпавшее правило) ---
    text_clean = normalize_text(text)
    raw_description = DEFAULT_DESCRIPTION
    for predicate, builder in OZON_DESCRIPTION_RULES:
        if predicate(text_clean):
            raw_description = builder(text)
            break

    return pd.Series({
        "source": "ozon",
        "date": date,
        "raw_amount": amount,
        "direction": direction,
        "raw_description": raw_description,
        "raw_category": RAW_CATEGORY,
    })


def parse_ozon_pdf(pdf_path: str) -> pd.DataFrame:
    payments = _extract_ozon_rows(pdf_path)

    df = pd.DataFrame({"text": payments})

    # первая строка — шапка таблицы
    df = df.iloc[1:].reset_index(drop=True)

    parsed = df["text"].apply(parse_ozon_row)
    result = pd.concat([df, parsed], axis=1)

    # оставляем только строки с распознанной суммой и убираем сырой текст
    result = result[result["raw_amount"].notna()].reset_index(drop=True)
    result = result.drop(columns=["text"])

    return result

import pandas as pd
import pdfplumber
import re

from .utils import RE_DATE, RE_SPACES, RE_OZON_AMOUNT
from pipeline.utils import normalize_text

def parse_ozon_pdf(pdf_path: str) -> pd.DataFrame:
    payments = []

    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages):

            rects = page.rects

            # --- 1. горизонтальные линии ---
            h_rects = [r for r in rects if r["height"] < 2]

            if not h_rects:
                continue

            df_rects = pd.DataFrame(h_rects)
            df_rects["top_round"] = df_rects["top"].round(1)

            line_positions = (
                df_rects
                .groupby("top_round")
                .agg({"width": "sum"})
                .reset_index()
            )

            line_positions = line_positions[
                line_positions["width"] > page.width * 0.3
            ]

            if len(line_positions) < 2:
                continue

            line_positions = line_positions.sort_values("top_round")
            tops = line_positions["top_round"].tolist()

            # --- 2. режем на строки ---
            for i in range(len(tops) - 1):
                top = tops[i]
                bottom = tops[i + 1]

                if bottom - top < 10:
                    continue

                bbox = (0, top, page.width, bottom)
                text = page.within_bbox(bbox).extract_text()

                if text and text.strip():
                    payments.append(RE_SPACES.sub(" ", text.strip()))

    df = pd.DataFrame({"text": payments})

    # --- 3. убираем первую строку (шапку) ---
    df = df.iloc[1:].reset_index(drop=True)

    # =====================================================
    # ПАРСИНГ СТРОК
    # =====================================================

    def parse_row(text: str):

        # --- amount + direction ---
        amount_match = RE_OZON_AMOUNT.search(text)

        if amount_match:
            direction = amount_match.group(1)
            amount = float(
                amount_match.group(2)
                .replace(" ", "")
                .replace(",", ".")
            )
        else:
            direction = None
            amount = None

        # --- date ---
        date_match = RE_DATE.search(text)
        date = pd.to_datetime(date_match.group(), dayfirst=True) if date_match else None

        # --- description ---
        # text_clean = re.sub(r"\s+", " ", text).lower()
        text_clean = normalize_text(text)

        if "возврат" in text_clean:
            raw_description = "Ozon. Возврат"

        elif "чаев" in text_clean:
            raw_description = "Ozon. Чаевые"

        elif "сбп" in text_clean and "отправитель" in text_clean:

            m = re.search(
                r"Отправитель:\s*([А-ЯЁ][а-яё]+ [А-ЯЁ][а-яё]+ [А-ЯЁ]\.)",
                text
            )
            sender = m.group(1) if m else ""
            raw_description = f"Ozon. СБП перевод от {sender}".strip()


        elif "остатка эдс" in text_clean:
            raw_description = f"Ozon. Перевод остатка между счетами".strip()

        elif "зачисление средств с использованием карты" in text_clean:
            raw_description = "Ozon. Зачисление с карты"

        elif "оплата товаров" in text_clean:
            raw_description = "Ozon. Оплата"

        else:
            raw_description = "Ozon"

        return pd.Series({
            "source": "ozon",
            "date": date,
            "raw_amount": amount,
            "direction": direction,
            "raw_description": raw_description,
            "raw_category": "Маркетплейсы"
        })

    parsed = df["text"].apply(parse_row)

    result = pd.concat([df, parsed], axis=1)

    # --- 5. оставляем только строки с суммой ---
    result = result[result["raw_amount"].notna()].reset_index(drop=True)

    # --- 6. удаляем сырой текст ---
    result = result.drop(columns=["text"])

    return result
"""Проверка покрытия категоризации.

Правила покрывают не все транзакции. Категория при непокрытии дефолтится на сырую
банковскую (`raw_category`, заполнена всегда), а подкатегория остаётся пустой —
это «дыра». Модуль считает покрытие по подкатегориям, находит дыры и генерирует
YAML-заготовки правил под вставку в `configs/categories.yaml`.

Дыры группируются по стабильному сигналу — банковской `raw_category` (описания
транзакций нестабильны: терминалы/написания меняются, поэтому дедуп по описанию
не работает). Финальный шаг `fill_default_subcategory` заполняет оставшиеся дыры
универсальным «Прочее», чтобы итоговый датасет был полным.
"""
from __future__ import annotations

import pandas as pd
import yaml

DEFAULT_SUBCATEGORY = "Прочее"
SUGGESTION_PRIORITY = 50

SUGGESTIONS_HEADER = """\
# Заготовки правил для недоразмеченных транзакций (подкатегория не покрыта правилами).
# По одному широкому правилу на банковскую категорию (conditions.category).
# Как использовать: поправь new_category/name под свою иерархию и перенеси блок
# в configs/categories.yaml. Файл перегенерируется при каждом прогоне с дырами.
"""


def coverage_stats(df: pd.DataFrame) -> tuple[int, int, float]:
    """Возвращает (покрыто, всего, доля) по непустой подкатегории."""
    total = len(df)
    if total == 0:
        return 0, 0, 1.0
    covered = int(df["subcategory"].notna().sum())
    return covered, total, covered / total


def find_gaps(df: pd.DataFrame) -> pd.DataFrame:
    """Недоразмеченные строки, сгруппированные по (source, банковская raw_category)."""
    gap = df[df["subcategory"].isna()]
    if gap.empty:
        return pd.DataFrame()

    return (
        gap.groupby(["source", "raw_category"])
        .agg(operations=("raw_amount", "size"), total_amount=("raw_amount", "sum"))
        .reset_index()
        .sort_values("total_amount", ascending=False)
        .reset_index(drop=True)
    )


def build_suggestions(gaps: pd.DataFrame) -> str:
    """YAML-текст заготовок правил (одно широкое правило на банковскую категорию)."""
    stubs = [
        {
            "name": DEFAULT_SUBCATEGORY,
            "new_category": row["raw_category"],
            "priority": SUGGESTION_PRIORITY,
            "conditions": {"category": [row["raw_category"]]},
        }
        for _, row in gaps.iterrows()
    ]
    body = yaml.dump(stubs, allow_unicode=True, sort_keys=False, default_flow_style=False)
    return SUGGESTIONS_HEADER + "\n" + body


def fill_default_subcategory(df: pd.DataFrame) -> pd.DataFrame:
    """Заполняет оставшиеся дыры подкатегории значением 'Прочее' (финальный шаг)."""
    df = df.copy()
    df["subcategory"] = df["subcategory"].fillna(DEFAULT_SUBCATEGORY)
    return df

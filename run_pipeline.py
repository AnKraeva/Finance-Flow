from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

INPUT_SUBDIR = "input"
OUTPUT_SUBDIR = "output"

CACHE_NAME = "parsed.csv"                 # временный кэш парсинга (удаляется в конце)
SUGGESTIONS_NAME = "suggested_rules.yaml"


def build_default_output_path(data_dir: str = "data") -> str:
    # Каждый датасет самодостаточен: данные читаются из <data-dir>/input,
    # результат кладётся рядом в <data-dir>/output. Файл один и перезаписывается
    # при каждом прогоне.
    return str(Path(data_dir) / OUTPUT_SUBDIR / "transactions.csv")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Parse personal finance statements and build a normalized dataset."
    )
    parser.add_argument(
        "--data-dir",
        default="data",
        help=(
            "Dataset folder. Statements are read from <data-dir>/input and the "
            "result is written to <data-dir>/output."
        ),
    )
    parser.add_argument(
        "--types-config",
        default="configs/types.yaml",
        help="Path to the transaction type rules YAML file.",
    )
    parser.add_argument(
        "--categories-config",
        default="configs/categories.yaml",
        help="Path to the category rules YAML file.",
    )
    parser.add_argument(
        "--output-csv",
        default=None,
        help="Where to save the result CSV. Defaults to <data-dir>/output/transactions.csv.",
    )
    return parser


def _transform(parsed, types_config: str, categories_config: str):
    """Дешёвый слой: типизация → категоризация → возвраты → фильтр внутренних.

    Перечитывает конфиги при каждом вызове, поэтому его можно гонять повторно
    (интерактивная рекатегоризация) по одному и тому же распарсенному датасету
    без повторного парсинга PDF. Не мутирует переданный `parsed`.
    """
    from pipeline.categorization import assign_categories
    from pipeline.typification import assign_refunds, assign_types
    from pipeline.utils import load_yaml

    type_rules = load_yaml(types_config)
    category_rules = load_yaml(categories_config)

    df = assign_types(parsed.copy(), type_rules)
    logger.info("[TYPES] distribution: %s", df["type"].value_counts().to_dict())

    df = assign_categories(df, category_rules)
    logger.info("[CATEGORIES] unique categories: %s", df["category"].nunique())

    df = assign_refunds(df, type_rules)
    logger.info("[REFUNDS] total refunds: %s", (df["type"] == "возврат").sum())

    before = len(df)
    df = df[df["type"] != "внутренний"]
    logger.info("[FILTER] internal transfers removed: %s | remaining: %s", before - len(df), len(df))

    return df.drop(columns=["direction"], errors="ignore")


def _write_suggestions(df, output_dir: Path) -> Path:
    """Пишет заготовки правил по дырам; при их отсутствии удаляет старый файл."""
    from pipeline.coverage import build_suggestions, find_gaps

    path = output_dir / SUGGESTIONS_NAME
    gaps = find_gaps(df)
    if gaps.empty:
        path.unlink(missing_ok=True)
    else:
        path.write_text(build_suggestions(gaps), encoding="utf-8")
    return path


def _interactive_loop(cache_path: Path, types_config: str, categories_config: str, output_dir: Path):
    """Ждёт правок правил и пересчитывает категоризацию по кэшу, пока не 100% или 'q'."""
    import pandas as pd

    from pipeline.coverage import coverage_stats

    while True:
        parsed = pd.read_csv(cache_path, parse_dates=["date"])
        df = _transform(parsed, types_config, categories_config)
        covered, total, ratio = coverage_stats(df)
        suggestions_path = _write_suggestions(df, output_dir)

        if covered == total:
            logger.info("[COVERAGE] 100%% — все транзакции размечены")
            return df

        print(
            f"\nПокрытие подкатегорий: {ratio * 100:.2f}% — недоразмечено {total - covered}.\n"
            f"Заготовки правил: {suggestions_path}\n"
            f"Поправь {categories_config} и нажми Enter для пересчёта, либо 'q' чтобы закончить: ",
            end="",
        )
        try:
            answer = input().strip().lower()
        except EOFError:
            answer = "q"
        if answer == "q":
            return df


def run_pipeline(
    data_dir: str,
    types_config: str,
    categories_config: str,
    interactive: bool | None = None,
):
    from pipeline.coverage import coverage_stats, fill_default_subcategory
    from pipeline.parsing import parse_folder

    parsed = parse_folder(str(Path(data_dir) / INPUT_SUBDIR))
    if parsed.empty:
        logger.warning("No data found for processing.")
        return parsed

    logger.info("[START] rows: %s", len(parsed))

    output_dir = Path(data_dir) / OUTPUT_SUBDIR
    cache_path = output_dir / CACHE_NAME

    try:
        df = _transform(parsed, types_config, categories_config)
        covered, total, ratio = coverage_stats(df)
        logger.info("[COVERAGE] subcategory: %s/%s (%.2f%%)", covered, total, ratio * 100)

        if covered < total:
            output_dir.mkdir(parents=True, exist_ok=True)
            parsed.to_csv(cache_path, index=False)   # временный кэш для пересчёта

            if interactive is None:
                interactive = sys.stdin.isatty()

            if interactive:
                df = _interactive_loop(cache_path, types_config, categories_config, output_dir)
            else:
                path = _write_suggestions(df, output_dir)
                logger.warning(
                    "[COVERAGE] недоразмечено %s строк — интерактив пропущен (не tty). Заготовки: %s",
                    total - covered,
                    path,
                )

        df = fill_default_subcategory(df)
        logger.info("[END] final rows: %s", len(df))
        return df
    finally:
        cache_path.unlink(missing_ok=True)


def main() -> None:
    args = build_parser().parse_args()

    from pipeline.logger import setup_logger

    setup_logger()

    df = run_pipeline(
        data_dir=args.data_dir,
        types_config=args.types_config,
        categories_config=args.categories_config,
    )

    if df.empty:
        return

    output_csv = args.output_csv or build_default_output_path(args.data_dir)
    output_path = Path(output_csv)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False)
    logger.info("[CSV] saved processed dataset to %s", output_path)


if __name__ == "__main__":
    main()

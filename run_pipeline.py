from __future__ import annotations

import argparse
import logging
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

INPUT_SUBDIR = "input"
OUTPUT_SUBDIR = "output"


def build_default_output_path(data_dir: str = "data") -> str:
    # Каждый датасет самодостаточен: данные читаются из <data-dir>/input,
    # результат кладётся рядом в <data-dir>/output с датой и временем в имени.
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    return str(Path(data_dir) / OUTPUT_SUBDIR / f"transactions_{timestamp}.csv")


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
        help="Where to save the result CSV. Defaults to a timestamped file in <data-dir>/output/.",
    )
    return parser


def run_pipeline(
    data_dir: str,
    types_config: str,
    categories_config: str,
):
    from pipeline.categorization import assign_categories
    from pipeline.parsing import parse_folder
    from pipeline.typification import assign_refunds, assign_types
    from pipeline.utils import load_yaml

    df = parse_folder(str(Path(data_dir) / INPUT_SUBDIR))

    if df.empty:
        logger.warning("No data found for processing.")
        return df

    type_rules = load_yaml(types_config)
    category_rules = load_yaml(categories_config)

    logger.info("[START] rows: %s", len(df))

    df = assign_types(df, type_rules)
    logger.info(
        "[TYPES] rows: %s | distribution: %s",
        len(df),
        df["type"].value_counts().to_dict(),
    )

    df = assign_categories(df, category_rules)
    logger.info("[CATEGORIES] unique categories: %s", df["category"].nunique())

    df = assign_refunds(df, type_rules)
    logger.info("[REFUNDS] total refunds: %s", (df["type"] == "возврат").sum())

    before = len(df)
    df = df[df["type"] != "внутренний"]
    after = len(df)
    logger.info("[FILTER] internal transfers removed: %s | remaining: %s", before - after, after)

    df = df.drop(columns=["direction"], errors="ignore")
    logger.info("[CLEAN] dropped columns: direction")
    logger.info("[END] final rows: %s", len(df))

    return df


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

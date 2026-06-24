import pandas as pd
import os
import re

import logging
logger = logging.getLogger(__name__)


from parsers import PARSERS

# =========================================================
# ОБХОД ПАПКИ С ВЫПИСКАМИ
# =========================================================

def parse_folder(folder_path: str) -> pd.DataFrame:

    all_dfs = []

    total_files = 0
    processed_files = 0
    skipped_files = 0
    error_files = 0

    for filename in os.listdir(folder_path):

        # молча пропускаем скрытые/системные файлы (.DS_Store, .Rhistory и т.п.)
        if filename.startswith("."):
            continue

        total_files += 1

        file_path = os.path.join(folder_path, filename)
        filename_lower = filename.lower()

        first_word = re.split(r"[ _\-]", filename_lower)[0]

        try:
            if filename_lower.endswith(".pdf"):
                ext = "pdf"
            elif filename_lower.endswith(".csv"):
                ext = "csv"
            else:
                logger.warning(f"{filename} — неподдерживаемый формат")
                skipped_files += 1
                continue

            parser = PARSERS.get(ext, {}).get(first_word)

            if not parser:
                logger.warning(f"{filename} — нет парсера")
                skipped_files += 1
                continue

            # logger.info(f"[{ext.upper()}] Обрабатываю: {filename}")

            df = parser(file_path)
            all_dfs.append(df)

            processed_files += 1

            logger.info(f"{filename} — {len(df)} строк")

        except Exception as e:
            error_files += 1
            logger.error(f"{filename}: {e}")

    logger.info("========== SUMMARY ==========")
    logger.info(f"Всего файлов: {total_files}")
    logger.info(f"Обработано: {processed_files}")
    logger.info(f"Пропущено: {skipped_files}")
    logger.info(f"С ошибкой: {error_files}")

    if all_dfs:
        result = pd.concat(all_dfs, ignore_index=True)
        logger.info(f"Итоговый DataFrame: {len(result)} строк")
        return result

    logger.warning("Нет данных")
    return pd.DataFrame()
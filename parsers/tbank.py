import pandas as pd

def parse_tbank_csv(file_path: str) -> pd.DataFrame:

    df = pd.read_csv(
        file_path,
        sep=";",
        engine="python",
        on_bad_lines="warn"
    ).query("Статус == 'OK'")

    mapping = {
        'Дата операции': 'date',
        'Категория': 'raw_category',
        'Сумма операции': 'raw_amount',
        'Описание': 'raw_description'
    }

    df = df.rename(columns=mapping)[list(mapping.values())]

    df['source'] = 'tbank'
    df['date'] = pd.to_datetime(df['date'], format='%d.%m.%Y %H:%M:%S').dt.normalize()

    df['direction'] = df['raw_amount'].apply(lambda x: '-' if '-' in str(x) else '+')
    df['raw_amount'] = (
        df['raw_amount']
        .astype(str)
        .str.replace(',', '.')
        .str.replace('-', '')
        .astype(float)
        .round(2)
    )

    return df
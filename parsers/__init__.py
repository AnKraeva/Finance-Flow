from .sber import parse_sber_pdf
from .tbank import parse_tbank_csv
from .ozon import parse_ozon_pdf


PARSERS = {
    "pdf": {
        "sber": parse_sber_pdf,
        "ozon": parse_ozon_pdf,
    },
    "csv": {
        "tbank": parse_tbank_csv,
    }
}

import yaml

# normalize_text живёт в нижнем слое (parsers), здесь реэкспортируется для
# обратной совместимости импортов внутри pipeline.
from parsers.utils import normalize_text  # noqa: F401


def load_yaml(path: str):
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

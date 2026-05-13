from pathlib import Path

from app.core.config import settings


DEFAULT_STOP_WORDS = {
    "комплект",
    "набор",
    "деталь",
    "элемент",
}


def _stop_words_path() -> Path:
    root = Path(settings.storage_root)
    root.mkdir(parents=True, exist_ok=True)
    return root / "matching_stop_words.txt"


def load_stop_words() -> list[str]:
    path = _stop_words_path()
    if not path.exists():
        return sorted(DEFAULT_STOP_WORDS)
    words = []
    for line in path.read_text(encoding="utf-8").splitlines():
        w = line.strip().lower()
        if w:
            words.append(w)
    return sorted(set(words))


def save_stop_words(words: list[str]) -> list[str]:
    normalized = sorted({str(w).strip().lower() for w in words if str(w).strip()})
    path = _stop_words_path()
    path.write_text("\n".join(normalized), encoding="utf-8")
    return normalized

import re


TRANSLIT_MAP = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d",
    "е": "e", "ё": "e", "ж": "zh", "з": "z", "и": "i",
    "й": "i", "к": "k", "л": "l", "м": "m", "н": "n",
    "о": "o", "п": "p", "р": "r", "с": "s", "т": "t",
    "у": "u", "ф": "f", "х": "h", "ц": "ts", "ч": "ch",
    "ш": "sh", "щ": "sch", "ъ": "", "ы": "y", "ь": "",
    "э": "e", "ю": "yu", "я": "ya",
}


def translit_ru(text: str) -> str:
    text = text.lower().strip()
    return "".join(TRANSLIT_MAP.get(ch, ch) for ch in text)


def normalize_part(text: str) -> str:
    text = translit_ru(text)
    return re.sub(r"[^a-z0-9]+", "", text)


def build_username(last_name: str, first_name: str, middle_name: str = "") -> str:
    last = normalize_part(last_name)
    first_initial = normalize_part(first_name[:1]) if first_name else ""
    middle_initial = normalize_part(middle_name[:1]) if middle_name else ""

    initials = ".".join(part for part in [first_initial, middle_initial] if part)

    if initials and last:
        return f"{initials}.{last}"
    if last:
        return last
    return "user"
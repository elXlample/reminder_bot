from .cmd import RU, EN


def get_translations() -> dict[str, str | dict[str, str]]:
    return {
        "default": "en",
        "en": EN,
        "ru": RU,
    }

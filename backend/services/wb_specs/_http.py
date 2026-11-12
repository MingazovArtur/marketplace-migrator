"""HTTP-слой Content API Wildberries: сырой токен без схемы Bearer/OAuth[cite: 12]."""

WB_API_BASE = "https://content-api.wildberries.ru"


def _wb_headers(token: str) -> dict:
    """WB принимает сырой токен без схемы Bearer/OAuth[cite: 12]."""
    return {
        "Authorization": token,
        "Accept": "application/json",
        "Content-Type": "application/json",
    }

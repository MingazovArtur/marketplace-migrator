"""HTTP-слой Partner API Яндекс Маркета: заголовки и POST с retry."""

import asyncio
import logging

import httpx

logger = logging.getLogger(__name__)

YANDEX_API_BASE = "https://api.partner.market.yandex.ru"

CONCURRENCY = 4          # одновременных запросов параметров категорий
TIMEOUT = 60.0           # таймаут одного HTTP-запроса
MAX_RETRIES = 3


def _ym_headers(token: str) -> dict:
    """
    Формирует заголовки авторизации Яндекс Маркета:
    - Новые токены (ACMA:...) передаются в заголовке 'Api-Key'
    - Старые OAuth-токены (y0_...) — в 'Authorization: OAuth <token>'
    """
    clean = (token or "").strip()
    if clean.lower().startswith("oauth "):
        clean = clean[6:].strip()
        return {
            "Authorization": f"OAuth {clean}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
    if clean.startswith("y0_"):
        return {
            "Authorization": f"OAuth {clean}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
    return {
        "Api-Key": clean,
        "Accept": "application/json",
        "Content-Type": "application/json",
    }


async def _post_ym(
    client: httpx.AsyncClient,
    sem: asyncio.Semaphore,
    path: str,
    body: dict,
    headers: dict,
) -> dict:
    """POST-запрос к Partner API Яндекс Маркета с семафором и retry на 420/429/5xx."""
    async with sem:
        last_err = None
        delay = 1.0
        for attempt in range(MAX_RETRIES):
            try:
                resp = await client.post(f"{YANDEX_API_BASE}{path}", json=body, headers=headers)
                if resp.status_code in (420, 429) or resp.status_code >= 500:
                    logger.warning(
                        f"⚠️ Yandex API {resp.status_code} на {path} (попытка {attempt + 1}/{MAX_RETRIES})"
                    )
                    await asyncio.sleep(delay)
                    delay *= 2
                    continue
                resp.raise_for_status()
                return resp.json()
            except httpx.HTTPStatusError as e:
                if e.response.status_code in (420, 429) or e.response.status_code >= 500:
                    last_err = e
                    await asyncio.sleep(delay)
                    delay *= 2
                    continue
                raise
            except (httpx.TransportError, httpx.TimeoutException, OSError) as e:
                last_err = e
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(delay)
                    delay *= 2
                continue
        raise last_err or httpx.HTTPError(f"Max retries exceeded для {path}")

"""HTTP-слой загрузчика спеков Ozon: заголовки, разбор API-ключа, POST с retry.

Константы политики HTTP (CONCURRENCY/TIMEOUT/MAX_RETRIES) живут здесь —
оркестратор _refresh берёт их отсюда. Вынесено без изменений из монолита
services/ozon_specs.py (Р8).
"""

import asyncio
import logging

import httpx

logger = logging.getLogger(__name__)

OZON_API_BASE = "https://api-seller.ozon.ru"

# =====================================================================
# Конфигурация параллелизма (ОПТИМИЗИРОВАНО ДЛЯ ПАМЯТИ)
# =====================================================================
CONCURRENCY = 5  # одновременных запросов к API Ozon (было 15)
TIMEOUT = 60.0  # таймаут одного запроса
MAX_RETRIES = 3  # попыток на запрос


def _ozon_headers(client_id: str, api_key: str) -> dict:
    """Ozon требует Client-Id + Api-Key (не Bearer!)."""
    return {
        "Client-Id": client_id,
        "Api-Key": api_key,
        "Content-Type": "application/json",
    }


def _parse_ozon_key(raw_key: str) -> tuple[str, str]:
    """
    Ключ Ozon: 'CLIENT_ID:API_KEY'.
    CLIENT_ID — число, API_KEY — UUID.
    """
    raw_key = (raw_key or "").strip()
    if ":" not in raw_key:
        raise ValueError(
            "Формат ключа Ozon: 'CLIENT_ID:API_KEY', например "
            "'1234567:e30b97e3-997e-4574-8ddf-56466bcd20b8'. "
            "Оба значения — в кабинете Ozon: Настройки → API-ключи."
        )
    client_id, api_key = raw_key.split(":", 1)
    client_id = client_id.strip()
    api_key = api_key.strip()

    if not client_id.isdigit():
        raise ValueError(
            f"Client ID должен быть ЧИСЛОМ, получено: '{client_id}'. "
            "Укажите числовой ID из кабинета Ozon (Настройки → API-ключи)."
        )
    if not api_key:
        raise ValueError("После двоеточия пустой API-ключ.")
    return client_id, api_key


async def _post(
    client: httpx.AsyncClient,
    sem: asyncio.Semaphore,
    path: str,
    body: dict,
    headers: dict,
) -> dict:
    """POST с семафором (ограничение конкурентности) и retry на 429/5xx/транспорт."""
    async with sem:
        last_err = None
        delay = 1.0
        for attempt in range(MAX_RETRIES):
            try:
                resp = await client.post(f"{OZON_API_BASE}{path}", json=body, headers=headers)
                if resp.status_code == 429 or resp.status_code >= 500:
                    logger.warning(
                        f"⚠️ Ozon {resp.status_code} на {path} (попытка {attempt + 1}/{MAX_RETRIES})"
                    )
                    await asyncio.sleep(delay)
                    delay *= 2
                    continue
                resp.raise_for_status()
                return resp.json()
            except httpx.HTTPStatusError as e:
                if e.response.status_code in (429,) or e.response.status_code >= 500:
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

"""
Общая SSRF-защита для всех внешних загрузок (фото товаров, YML-фиды и т.д.).

Основана на parsers/yml_parser.validate_url() и усилена:
  - блокировка IPv4-mapped IPv6 (::ffff:127.0.0.1) и unspecified (0.0.0.0);
  - явные IP в URL проверяются без DNS (например, http://169.254.169.254/);
  - safe_get() валидирует КАЖДЫЙ переход редиректа (allow_redirects=False),
    а не только исходный адрес.

E-4 (неделя 4): защита от DNS-rebinding (TOCTOU). Раньше между проверкой DNS
и самим запросом атакующий DNS-сервер мог «переключить» запись с публичного
адреса на внутренний. Теперь safe_get() резолвит имя ОДИН раз, валидирует все
записи и ПИННИТ их на время запроса: обёртка вокруг socket.getaddrinfo
подставляет только что валидированные IP, поэтому соединение физически не
может уйти на адрес, отличный от проверенного. Подход сохраняет SNI,
проверку TLS-сертификата и заголовок Host без изменений (в отличие от
подключения по IP с Host-заголовком, где CDN без SNI не отдают сертификат).

Публичный API: validate_url / assert_safe_url / safe_get.
"""

import ipaddress
import logging
import socket
import threading
from contextlib import contextmanager
from urllib.parse import urlparse

import httpx

logger = logging.getLogger(__name__)

ALLOWED_SCHEMES = ("http", "https")

# Имена хостов, которые резолвятся внутри Docker-сети приложения
FORBIDDEN_HOSTNAMES = {
    "localhost",
    "db",
    "postgres",
    "redis",
    "backend",
    "celery",
    "celery_worker",
    "nginx",
    "kafka",
    "rabbitmq",
}

MAX_REDIRECTS = 3


def _is_forbidden_ip(ip_obj) -> bool:
    """Проверяет IP на принадлежность внутренним/служебным диапазонам."""
    # IPv4-mapped IPv6 (::ffff:10.0.0.1) — is_private у IPv6Address его не видит
    if isinstance(ip_obj, ipaddress.IPv6Address):
        mapped = getattr(ip_obj, "ipv4_mapped", None)
        if mapped is not None:
            ip_obj = mapped
    return (
        ip_obj.is_private
        or ip_obj.is_loopback
        or ip_obj.is_link_local
        or ip_obj.is_multicast
        or ip_obj.is_reserved
        or ip_obj.is_unspecified
    )


# ---------------------------------------------------------------------------
# E-4: DNS-pinning — пиннинг валидированных IP на время запроса.
#
# socket.getaddrinfo обёрнут глобально один раз (лениво, при первом пине).
# Обёртка прозрачна для всех остальных имён: без активного пина она
# делегирует оригинальной функции. Для запиненного имени она возвращает
# ТОЛЬКО валидированные IP (вызов getaddrinfo для IP-литерала не делает
# DNS-запрос), поэтому и httpcore (socket.create_connection в sync-бэкенде),
# и любыеio (в async-бэкенде) соединяются строго с проверенным адресом.
# ---------------------------------------------------------------------------

_pin_lock = threading.Lock()
_pinned_ips: dict[str, list[str]] = {}  # hostname (lower) -> валидированные IP
_pin_patch_installed = False
_real_getaddrinfo = socket.getaddrinfo


def _pinned_getaddrinfo(host, *args, **kwargs):
    """Обёртка getaddrinfo: для запиненных имён отдаёт только валидированные IP."""
    if isinstance(host, bytes):
        try:
            key = host.decode("idna")
        except Exception:
            key = host.decode("utf-8", "replace")
    else:
        key = host
    ips = _pinned_ips.get(str(key).lower())
    if ips:
        result = []
        for ip in ips:
            # getaddrinfo для IP-литерала не ходит в DNS и корректно
            # обрабатывает family/type/proto из аргументов вызова
            result.extend(_real_getaddrinfo(ip, *args, **kwargs))
        return result
    return _real_getaddrinfo(host, *args, **kwargs)


def _ensure_pin_patch_installed():
    """Однократная установка обёртки (идемпотентно, потокобезопасно)."""
    global _pin_patch_installed, _real_getaddrinfo
    with _pin_lock:
        if _pin_patch_installed:
            return
        if socket.getaddrinfo is not _pinned_getaddrinfo:
            _real_getaddrinfo = socket.getaddrinfo
            socket.getaddrinfo = _pinned_getaddrinfo
            _pin_patch_installed = True


@contextmanager
def _pinned_dns(hostname: str, ips: list[str]):
    """
    На время контекста DNS-имя hostname резолвится ТОЛЬКО в ips.

    Запись идемпотентна: параллельные пины одного имени не ломают друг друга
    (последний выигрывает; снимается только своя запись).
    """
    key = (hostname or "").lower()
    if not key or not ips:
        yield
        return
    _ensure_pin_patch_installed()
    with _pin_lock:
        _pinned_ips.setdefault(key, list(ips))
    try:
        yield
    finally:
        with _pin_lock:
            if _pinned_ips.get(key) == ips:
                del _pinned_ips[key]


def _validate_and_resolve(url: str) -> tuple[str, list[str]]:
    """
    Полная проверка URL + ОДНО DNS-разрешение (для пиннинга).

    Возвращает (hostname, валидированные публичные IP-адреса).
    Бросает ValueError с причиной, если URL запрещён:
      1) схема не http/https;
      2) зарезервированное имя хоста (localhost, db, redis, ...);
      3) явный внутренний IP в URL;
      4) DNS-имя резолвится хотя бы в один внутренний/служебный IP.
    """
    try:
        result = urlparse(url)
        if result.scheme not in ALLOWED_SCHEMES:
            raise ValueError(f"схема не http/https — {url!r}")
        hostname = result.hostname
        if not hostname:
            raise ValueError(f"нет имени хоста — {url!r}")

        if hostname.lower() in FORBIDDEN_HOSTNAMES:
            raise ValueError(f"запрещённое имя хоста {hostname}")

        # Явный IP-адрес в URL — проверяем без DNS
        try:
            ip_obj = ipaddress.ip_address(hostname)
        except ValueError:
            pass
        else:
            if _is_forbidden_ip(ip_obj):
                raise ValueError(f"внутренний IP в URL — {hostname}")
            return hostname, [hostname]

        # DNS-имя: ОДНО разрешение, проверяем ВСЕ записи (A/AAAA)
        addr_info = socket.getaddrinfo(hostname, None)
        ips: list[str] = []
        seen: set[str] = set()
        for item in addr_info:
            ip_str = item[4][0]
            if _is_forbidden_ip(ipaddress.ip_address(ip_str)):
                raise ValueError(
                    f"хост {hostname} резолвится во внутренний IP {ip_str}"
                )
            if ip_str not in seen:
                seen.add(ip_str)
                ips.append(ip_str)
        if not ips:
            raise ValueError(f"хост {hostname} не резолвится")
        return hostname, ips
    except ValueError:
        raise
    except Exception as e:
        raise ValueError(f"ошибка SSRF-валидации URL {url!r}: {e}") from e


def validate_url(url: str) -> bool:
    """
    Проверяет, что URL безопасен для загрузки:
      1) использует http/https;
      2) не ведёт на зарезервированное имя (localhost, db, redis, ...);
      3) резолвится ТОЛЬКО в публичные IP (никаких приватных/loopback/link-local).

    Возвращает True, если URL безопасен.
    """
    try:
        _validate_and_resolve(url)
        return True
    except ValueError as e:
        logger.warning(f"🚫 SSRF block: {e}")
        return False


def assert_safe_url(url: str) -> None:
    """Валидация с исключением — удобно использовать в сервисах."""
    if not validate_url(url):
        raise ValueError(
            f"Небезопасный URL заблокирован (SSRF-защита): {url}. "
            "Разрешены только публичные http/https-адреса."
        )


def safe_get(
    url: str,
    *,
    session: httpx.Client | None = None,
    timeout: float = 15,
    headers: dict | None = None,
    stream: bool = True,
    max_redirects: int = MAX_REDIRECTS,
) -> httpx.Response:
    """
    Аналог httpx.get с SSRF-защитой:
      - исходный URL валидируется перед запросом (одно DNS-разрешение);
      - валидированные IP ПИННЯТСЯ на время запроса — защита от DNS-rebinding
        (E-4): даже если DNS «переключится» между проверкой и соединением,
        запрос уйдёт только на проверенный адрес;
      - редиректы обрабатываются вручную (follow_redirects по умолчанию
        выключен у httpx), каждый переход валидируется и пиннится заново.

    Бросает ValueError, если адрес запрещён.
    Возвращает response — только НЕ редирект (вызывающий обязан обработать
    raise_for_status / закрыть response при stream=True).
    """
    sess = session or httpx.Client()
    resp = None
    current_url = url
    for _ in range(max_redirects + 1):
        try:
            hostname, ips = _validate_and_resolve(current_url)
        except ValueError as e:
            raise ValueError(
                f"Запрещённый адрес (SSRF-защита): {current_url} — {e}"
            ) from e

        if resp is not None:
            resp.close()

        with _pinned_dns(hostname, ips):
            # stream=True обязателен для больших загрузок (лимит размера на лету);
            # follow_redirects у httpx по умолчанию выключен — редиректы валидируем сами
            req = sess.build_request("GET", current_url, headers=headers, timeout=timeout)
            resp = sess.send(req, stream=stream)
        if resp.is_redirect:
            next_url = resp.headers.get("Location", "")
            if not next_url:
                raise ValueError("Редирект без заголовка Location")
            current_url = next_url
            continue
        return resp

    if resp is not None:
        resp.close()
    raise ValueError(f"Превышен лимит редиректов ({max_redirects}) для {url}")

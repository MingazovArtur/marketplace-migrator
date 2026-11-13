"""Тесты SSRF-защиты (неделя 1) + DNS-pinning против DNS-rebinding (неделя 4, E-4).

Чистые проверки без сети: валидация URL, обработка редиректов (стаб-сессия),
пиннинг валидированных IP на время запроса.
"""

import socket

import httpx
import pytest

import core.ssrf as ssrf
from core.ssrf import safe_get, validate_url

CASES_BLOCK = [
    "http://169.254.169.254/latest/meta-data/",  # metadata AWS
    "http://127.0.0.1:8000/api/health",  # loopback v4
    "http://10.0.0.5/",  # частная 10/8
    "http://192.168.1.1/admin",  # частная 192.168/16
    "http://172.16.3.4/",  # частная 172.16/12
    "http://[::1]/",  # loopback v6
    "http://[::ffff:127.0.0.1]/",  # IPv4-mapped в v6
    "http://[::ffff:10.0.0.1]/",  # IPv4-mapped частная
    "http://0.0.0.0/",  # unspecified
    "http://localhost:8000/",  # localhost
    "http://db:5432/",  # docker-имя db
    "http://redis:6379/",  # docker-имя redis
    "http://backend:8000/",  # docker-имя backend
    "file:///etc/passwd",  # file:// схема
    "ftp://1.2.3.4/",  # ftp:// схема
    "gopher://x/",  # gopher://
    "",  # пустой URL
    "not a url",  # мусор
    "http://",  # нет хоста
]

CASES_ALLOW = [
    "http://8.8.8.8/",  # публичный IP
    "https://1.1.1.1/",  # публичный IP https
]


@pytest.mark.parametrize("url", CASES_BLOCK)
def test_validate_url_blocks(url):
    assert validate_url(url) is False


@pytest.mark.parametrize("url", CASES_ALLOW)
def test_validate_url_allows(url):
    assert validate_url(url) is True


def test_safe_get_blocks_metadata_before_any_request():
    """Запрещённый адрес блокируется ДО любого сетевого запроса."""
    with pytest.raises(ValueError, match="SSRF"):
        safe_get("http://169.254.169.254/", timeout=1)


def test_safe_get_blocks_localhost():
    with pytest.raises(ValueError, match="SSRF"):
        safe_get("http://localhost:8000/", timeout=1)


# ---------------------------------------------------------------------------
# Редиректы: каждый переход валидируется заново
# ---------------------------------------------------------------------------


class _StubResponse:
    def __init__(self, status_code=302, location=None, is_redirect=None):
        self.status_code = status_code
        self.headers = {"Location": location} if location else {}
        if is_redirect is None:
            is_redirect = 300 <= status_code < 400 and location is not None
        self.is_redirect = is_redirect
        self.closed = False

    def close(self):
        self.closed = True


class _StubSession:
    """Стаб httpx.Client (контракт safe_get: build_request + send):
    отвечает заготовками по порядку, пишет журнал вызовов."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    def build_request(self, method, url, **kwargs):
        return method, url, kwargs

    def send(self, request, stream=False, **kwargs):
        method, url, kw = request
        self.calls.append((url, kw))
        return self._responses.pop(0)


def test_safe_get_validates_each_redirect_hop():
    """Редирект с публичного адреса на внутренний должен быть заблокирован."""
    stub = _StubSession([_StubResponse(location="http://127.0.0.1/secret")])
    with pytest.raises(ValueError, match="127.0.0.1"):
        safe_get("http://8.8.8.8/step1", session=stub, timeout=1)
    # первый запрос прошёл (по публичному адресу), второй не выполнялся
    assert len(stub.calls) == 1


def test_safe_get_follows_safe_redirects():
    stub = _StubSession(
        [
            _StubResponse(location="http://8.8.8.8/step2"),
            _StubResponse(status_code=200, location=None),
        ]
    )
    resp = safe_get("http://8.8.8.8/step1", session=stub, timeout=1)
    assert resp.status_code == 200
    assert [c[0] for c in stub.calls] == ["http://8.8.8.8/step1", "http://8.8.8.8/step2"]


def test_safe_get_redirect_without_location_raises():
    # защитная ветка: ответ-редирект без заголовка Location
    stub = _StubSession([_StubResponse(status_code=302, location=None, is_redirect=True)])
    with pytest.raises(ValueError, match="Location"):
        safe_get("http://8.8.8.8/", session=stub, timeout=1)


def test_safe_get_redirect_loop_limit():
    stub = _StubSession([_StubResponse(location=f"http://8.8.8.8/hop{i}") for i in range(10)])
    with pytest.raises(ValueError, match="редирект"):
        safe_get("http://8.8.8.8/start", session=stub, timeout=1, max_redirects=3)
    assert len(stub.calls) == 4  # исходный + 3 перехода


# ---------------------------------------------------------------------------
# E-4 (неделя 4): DNS-rebinding (TOCTOU) — пиннинг валидированных IP
# ---------------------------------------------------------------------------

REBIND_HOST = "rebind.example"
PUBLIC_IP = "93.184.216.34"
REBOUND_IP = "169.254.169.254"  # «внутренний» адрес, на который DNS «переключается»


def _install_rebinding_dns(monkeypatch, public_for_n=1):
    """
    Имитирует DNS-сервер атакующего: первые public_for_n резолвов имени отдают
    публичный IP (окна валидации), все последующие — внутренний (ребайнд).
    Возвращает счётчик резолвов имени.
    """
    # настоящий getaddrinfo — именно внутренний real обёртки (не socket.getaddrinfo,
    # который мог быть уже заменён обёрткой пиннинга из предыдущих тестов)
    real_gai = ssrf._real_getaddrinfo
    counter = {"n": 0}

    def fake_getaddrinfo(host, *args, **kwargs):
        if isinstance(host, bytes):
            try:
                host = host.decode("idna")
            except Exception:
                host = host.decode("utf-8", "replace")
        if str(host).lower() == REBIND_HOST:
            counter["n"] += 1
            ip = PUBLIC_IP if counter["n"] <= public_for_n else REBOUND_IP
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 0))]
        return real_gai(host, *args, **kwargs)

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    monkeypatch.setattr(ssrf, "_real_getaddrinfo", fake_getaddrinfo)
    monkeypatch.setattr(ssrf, "_pin_patch_installed", False)
    return counter


def _record_socket_connections(monkeypatch):
    """Подменяет socket.socket: записывает адреса TCP-соединений, сеть не нужна."""
    connected = []

    class _FakeSocket:
        def __init__(self, family=socket.AF_INET, type=socket.SOCK_STREAM, proto=0, *a, **k):
            pass

        def settimeout(self, *a, **k):
            pass

        def setsockopt(self, *a, **k):
            pass

        def connect(self, address):
            connected.append(address)
            raise ConnectionRefusedError(f"test stub: no network, got {address}")

        def close(self):
            pass

    monkeypatch.setattr(socket, "socket", _FakeSocket)
    return connected


def test_dns_rebinding_blocked_by_pinning(monkeypatch):
    """Ядро E-4: соединение уходит ТОЛЬКО на валидированный IP,
    даже если DNS между проверкой и запросом «переключился» на внутренний."""
    _install_rebinding_dns(monkeypatch)
    connected = _record_socket_connections(monkeypatch)

    # Без пиннинга соединение ушло бы на 169.254.169.254 (второй резолв).
    with pytest.raises(httpx.TransportError):
        safe_get(f"http://{REBIND_HOST}/photo.jpg", timeout=2)

    assert connected, "соединение должно было быть попыткой TCP-подключения"
    target_ip = connected[0][0]
    assert target_ip == PUBLIC_IP, (
        f"DNS-rebinding не заблокирован: соединились с {target_ip}, "
        f"ожидали запинненный {PUBLIC_IP}"
    )
    # пин снят после запроса
    assert REBIND_HOST not in ssrf._pinned_ips


def test_dns_rebinding_blocked_on_redirect_hop(monkeypatch):
    """Пин обновляется на каждом переходе редиректа: оба окна валидации
    видят публичный IP, «атакующий» DNS переключается сразу после них —
    соединение hop-2 идёт только на валидированный IP."""

    class _HybridSession:
        """hop-1 отвечает стабом-редиректом, hop-2 идёт по реальному
        сетевому пути httpx/httpcore (fake DNS + fake socket)."""

        def __init__(self):
            self.hop = 0
            self._real = httpx.Client()

        def build_request(self, method, url, **kwargs):
            return method, url, kwargs

        def send(self, request, stream=False, **kwargs):
            method, url, kw = request
            self.hop += 1
            if self.hop == 1:
                return _StubResponse(location=f"http://{REBIND_HOST}/hop2")
            return self._real.send(self._real.build_request(method, url, **kw), stream=stream)

    _install_rebinding_dns(monkeypatch, public_for_n=2)
    connected = _record_socket_connections(monkeypatch)

    with pytest.raises(httpx.TransportError):
        safe_get(f"http://{REBIND_HOST}/hop1", session=_HybridSession(), timeout=2)

    # соединение состоялось и ушло только на валидированный IP
    assert connected, "должна была быть попытка TCP-соединения"
    assert all(addr[0] == PUBLIC_IP for addr in connected)


def test_pin_persists_for_uppercase_hostname(monkeypatch):
    """Пин ищется без учёта регистра (URL с REBIND.ExAMPLE)."""
    _install_rebinding_dns(monkeypatch)
    connected = _record_socket_connections(monkeypatch)
    with pytest.raises(httpx.TransportError):
        safe_get(f"http://{REBIND_HOST.upper()}/photo.jpg", timeout=2)
    assert connected and connected[0][0] == PUBLIC_IP


def test_pinned_dns_context_substitutes_resolution(monkeypatch):
    """Контекст-менеджер _pinned_dns: внутри контекста имя резолвится
    только в запинненные IP, после выхода пин снимается."""
    monkeypatch.setattr(ssrf, "_pin_patch_installed", False)
    with ssrf._pinned_dns(REBIND_HOST, [PUBLIC_IP]):
        infos = socket.getaddrinfo(REBIND_HOST, 80)
        assert {i[4][0] for i in infos} == {PUBLIC_IP}
    assert REBIND_HOST not in ssrf._pinned_ips


def test_validate_and_resolve_returns_all_public_ips(monkeypatch):
    """Все A/AAAA-записи публичны → возвращаются все; резолв единый."""
    real_gai = socket.getaddrinfo

    def fake_getaddrinfo(host, *args, **kwargs):
        if host == "multi.example":
            return [
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0)),
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.215.35", 0)),
            ]
        return real_gai(host, *args, **kwargs)

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    hostname, ips = ssrf._validate_and_resolve("http://multi.example/x")
    assert hostname == "multi.example"
    assert set(ips) == {"93.184.216.34", "93.184.215.35"}


def test_validate_and_resolve_raises_on_any_private_record(monkeypatch):
    real_gai = socket.getaddrinfo

    def fake_getaddrinfo(host, *args, **kwargs):
        if host == "mixed.example":
            return [
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0)),
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.1.2.3", 0)),
            ]
        return real_gai(host, *args, **kwargs)

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    with pytest.raises(ValueError, match="10.1.2.3"):
        ssrf._validate_and_resolve("http://mixed.example/x")

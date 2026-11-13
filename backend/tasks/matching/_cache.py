"""P-3: TTL-кэш справочника спеков площадки (5 минут, in-process).

Вынесено без изменений из монолита tasks/matching.py (Р20).

Проблема из ревью: _match_spec_by_text / _spec_name_exists /
_load_spec_for_category открывали СВОЮ сессию БД и выгружали ВСЕ имена
категорий площадки при КАЖДОМ вызове. Пакетная миграция 500 товаров →
тысячи сессий и полных выгрузок справочника (у Ozon это десятки тысяч
строк).

Спеки меняются только через refresh_specs_task — поэтому держим их в
памяти воркера с TTL 5 минут и сбрасываем после обновления спеков
(_spec_cache_invalidate вызывается задачей загрузки спеков).
"""

import time

_SPEC_CACHE_TTL = 300.0  # секунд
_spec_cache_names: dict = {}  # platform -> [category_name, ...]
_spec_cache_names_set: dict = {}  # platform -> {нормализованное имя, ...}
_spec_cache_specs: dict = {}  # platform -> {имя -> spec JSON}
_spec_cache_has: dict = {}  # platform -> bool (есть ли хоть один спек)
_spec_cache_ts: dict = {}  # platform -> время загрузки (monotonic)
_SPEC_CACHE_MAX_SPECS = 512  # предохранитель по памяти на площадку


def _spec_cache_invalidate(platform: str = None):
    """Сброс кэша (весь или по одной площадке). Вызывается refresh_specs_task."""
    stores = (
        _spec_cache_names,
        _spec_cache_names_set,
        _spec_cache_specs,
        _spec_cache_has,
        _spec_cache_ts,
    )
    if platform:
        for store in stores:
            store.pop(platform, None)
    else:
        for store in stores:
            store.clear()


def _spec_cache_load(platform: str):
    """Загружает имена категорий площадки ОДНИМ запросом (раз в TTL)."""
    ts = _spec_cache_ts.get(platform)
    if ts is not None and (time.monotonic() - ts) < _SPEC_CACHE_TTL:
        return

    from database.models import PlatformCategorySpec
    from database.session import SessionLocal

    db = SessionLocal()
    try:
        names = [
            n
            for (n,) in db.query(PlatformCategorySpec.category_name)
            .filter(PlatformCategorySpec.platform == platform)
            .all()
        ]
    finally:
        db.close()

    _spec_cache_names[platform] = names
    _spec_cache_names_set[platform] = {str(n).strip() for n in names}
    _spec_cache_specs[platform] = {}
    _spec_cache_has[platform] = bool(names)
    _spec_cache_ts[platform] = time.monotonic()


def _platform_has_any_specs(platform: str) -> bool:
    """Проверяет, загружена ли хотя бы одна спецификация для данной площадки в БД."""
    _spec_cache_load(platform)
    return _spec_cache_has.get(platform, False)


def _spec_name_exists(platform: str, name) -> bool:
    """Существует ли ТОЧНОЕ имя категории в спеках площадки (из кэша, без БД)."""
    if not name:
        return False
    _spec_cache_load(platform)
    return str(name).strip() in _spec_cache_names_set.get(platform, set())


def _load_spec_for_category(target_platform: str, category_name: str):
    """Загружает спек из БД по имени категории (P-3: с кэшем по имени). Возвращает JSON-dict или None."""
    if not category_name:
        return None

    _spec_cache_load(target_platform)
    key = str(category_name).strip()
    cache = _spec_cache_specs.setdefault(target_platform, {})
    if key in cache:
        return cache[key]

    from database.models import PlatformCategorySpec
    from database.session import SessionLocal

    db = SessionLocal()
    try:
        row = (
            db.query(PlatformCategorySpec)
            .filter(
                PlatformCategorySpec.platform == target_platform,
                PlatformCategorySpec.category_name == category_name,
            )
            .first()
        )
        spec = row.spec if row else None
    finally:
        db.close()

    # предохранитель по памяти: не копим безлимитный кэш JSON-спеков
    if len(cache) >= _SPEC_CACHE_MAX_SPECS:
        cache.clear()
    cache[key] = spec
    return spec

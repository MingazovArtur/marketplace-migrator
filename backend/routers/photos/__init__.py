"""
Роутер управления фотографиями товара: порядок, добавление по ссылке,
загрузка файлов с компьютера, скачивание копий и проксирование защищённых CDN.

Р21 (разбиение монолита routers/photos.py, 298 строк, на пакет — по
прецедентам routers/export/ (Р1), routers/products/ (Р10),
routers/import_router/ (Р13)):

  - _support.py   — лимиты (размер/количество/расширения), PhotosUpdate,
                    _build_public_media_url (полный публичный URL:
                    dev-фронт :5173 не подставляется в XLSX-экспорт)
  - _proxy.py     — GET /photos/proxy: прокси внешних CDN с SSRF-защитой
                    (K-1): safe_get, белый список Content-Type, лимит 10 МБ,
                    rate-limit 30/мин
  - _manage.py    — GET/PUT /{product_id}/photos: чтение и замена списка
                    (дедупликация URL, лимит 30 фото)
  - _upload.py    — POST /{product_id}/photos/upload: multipart-загрузка
                    с компьютера (JPG/PNG/WEBP, до 10 МБ, md5-имена)
  - _download.py  — POST /{product_id}/photos/download: локальные копии
                    внешних фото (независимость от блокировок чужих CDN)

Порядок include_router сохранён как порядок объявления в монолите
(proxy → manage → upload → download): фиксированный маршрут
/photos/proxy регистрируется ДО параметрических /{product_id}/photos,
матчинг маршрутов не изменился.

Публичный API сохранён: `from routers import photos; photos.router`
(main.py не менялся); эндпоинты, константы и PhotosUpdate реэкспорти-
рованы теми же объектами, что в подмодулях. Логгеры подмодулей —
иерархические дети «routers.photos» (routers.photos._proxy и т.д.).
"""

from fastapi import APIRouter

from routers.photos._download import router as download_router
from routers.photos._manage import router as manage_router
from routers.photos._proxy import router as proxy_router
from routers.photos._upload import router as upload_router

router = APIRouter(prefix="/api/products", tags=["Photos"])
router.include_router(proxy_router)
router.include_router(manage_router)
router.include_router(upload_router)
router.include_router(download_router)

# Публичные имена монолита для импортёров и тестов (те же объекты,
# что используют подмодули).
from routers.photos._download import start_download_photos  # noqa: E402
from routers.photos._manage import get_photos, set_photos  # noqa: E402
from routers.photos._proxy import (  # noqa: E402
    PROXY_ALLOWED_CONTENT_TYPES,
    PROXY_MAX_SIZE_BYTES,
    proxy_external_photo,
)
from routers.photos._support import (  # noqa: E402
    ALLOWED_EXTENSIONS,
    MAX_FILE_SIZE_BYTES,
    MAX_PHOTOS_PER_PRODUCT,
    PhotosUpdate,
    _build_public_media_url,
)
from routers.photos._upload import upload_photo_files  # noqa: E402

__all__ = [
    "router",
    "PhotosUpdate",
    "proxy_external_photo",
    "get_photos",
    "set_photos",
    "upload_photo_files",
    "start_download_photos",
    "ALLOWED_EXTENSIONS",
    "MAX_FILE_SIZE_BYTES",
    "MAX_PHOTOS_PER_PRODUCT",
    "PROXY_ALLOWED_CONTENT_TYPES",
    "PROXY_MAX_SIZE_BYTES",
    "_build_public_media_url",
]

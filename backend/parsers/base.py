"""
Абстрактный базовый класс для всех парсеров файлов.
Единый интерфейс для парсинга файлов разных площадок.
"""
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class ParseResult:
    """
    Стандартизированный результат парсинга.

    ✅ Совместим со словарным интерфейсом (result["products"], result.get(...)),
    чтобы не ломать существующий код в routers/import_router/
    (бывший import_router.py).
    """
    products: list[dict[str, Any]] = field(default_factory=list)
    errors: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[dict[str, Any]] = field(default_factory=list)
    total_rows: int = 0
    imported: int = 0
    failed: int = 0

    # ===== Словарный интерфейс для обратной совместимости =====
    def __getitem__(self, key: str):
        return getattr(self, key)

    def __contains__(self, key: str):
        return hasattr(self, key)

    def get(self, key: str, default=None):
        return getattr(self, key, default)

    def keys(self):
        return self.__dataclass_fields__.keys()

    def values(self):
        return [getattr(self, k) for k in self.keys()]

    def items(self):
        return [(k, getattr(self, k)) for k in self.keys()]

    def as_dict(self) -> dict[str, Any]:
        """Явное преобразование в словарь."""
        return asdict(self)


class BaseFileParser(ABC):
    """
    Базовый класс парсера файла маркетплейса.

    Все парсеры должны реализовать метод parse(), который принимает
    содержимое файла и возвращает стандартизированный ParseResult.
    """

    @abstractmethod
    def parse(self, file_content: bytes, file_type: str) -> ParseResult:
        """
        Парсит файл и возвращает результат.

        Args:
            file_content: Содержимое файла в байтах
            file_type: Тип файла ('xlsx', 'csv', 'yml')

        Returns:
            ParseResult со списком товаров и ошибками
        """
        pass

    @property
    @abstractmethod
    def platform(self) -> str:
        """Название площадки (ozon, wildberries, yandex, magnit)."""
        pass

    @property
    @abstractmethod
    def supported_formats(self) -> list[str]:
        """Поддерживаемые форматы файлов."""
        pass

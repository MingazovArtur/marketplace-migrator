"""R30 (С-7 ревью): ленивая чистка каталога экспортов (tasks/export_tasks.py).

Чистка — чистая функция от каталога и TTL: проверяется на tmp_path без
брокера и без /app/media/exports. Инварианты: удаляются только файлы
старше TTL, ошибки ввода-вывода не поднимаются наружу (задача экспорта
не должна падать из-за чистки), отсутствующий каталог — штатный ноль.
"""

import os
import time

from tasks.export_tasks import EXPORTS_TTL_SEC, _cleanup_old_exports


def _touch(path, mtime=None):
    path.write_bytes(b"x")
    if mtime is not None:
        os.utime(path, (mtime, mtime))


class TestCleanupOldExports:
    def test_removes_only_expired_files(self, tmp_path):
        expired = time.time() - EXPORTS_TTL_SEC - 60
        old = tmp_path / "aaa_old.xlsx"
        fresh = tmp_path / "bbb_fresh.xlsx"
        _touch(old, mtime=expired)
        _touch(fresh)

        removed = _cleanup_old_exports(tmp_path)

        assert removed == 1
        assert not old.exists()
        assert fresh.exists()

    def test_ttl_zero_removes_everything(self, tmp_path):
        for i in range(3):
            _touch(tmp_path / f"f{i}.xlsx")

        assert _cleanup_old_exports(tmp_path, ttl_sec=0) == 3
        assert not list(tmp_path.iterdir())

    def test_missing_dir_is_not_an_error(self, tmp_path):
        assert _cleanup_old_exports(tmp_path / "nope") == 0

    def test_directories_are_not_touched(self, tmp_path):
        # подкаталоги (вдруг появятся) чисткой не удаляются — только файлы
        (tmp_path / "nested").mkdir()
        expired = time.time() - EXPORTS_TTL_SEC - 60
        _touch(tmp_path / "old.xlsx", mtime=expired)

        assert _cleanup_old_exports(tmp_path) == 1
        assert (tmp_path / "nested").is_dir()

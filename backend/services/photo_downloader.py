import aiohttp
import os
from pathlib import Path
from typing import List
import logging
import time
import asyncio

logger = logging.getLogger(__name__)

class PhotoDownloader:
    """Сервис для скачивания фотографий товаров"""
    
    def __init__(self, base_dir: str = "photos"):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        
        # Заголовки для обхода защиты CDN
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "image/webp,image/apng,image/*,*/*;q=0.8",
            "Referer": "https://www.ozon.ru/"
        }
    
    async def download_photos(self, product_id: str, photo_urls: List[str]) -> dict:
        """
        Скачивает все фото товара в папку photos/{product_id}/
        """
        product_dir = self.base_dir / str(product_id)
        product_dir.mkdir(parents=True, exist_ok=True)
        
        downloaded = 0
        failed = 0
        skipped = 0
        local_paths = []
        
        for i, url in enumerate(photo_urls, 1):
            file_path = product_dir / f"photo_{i}.jpg"
            
            # Если файл уже существует — пропускаем
            if file_path.exists() and file_path.stat().st_size > 0:
                logger.info(f"Фото {i} уже существует, пропускаем")
                skipped += 1
                local_paths.append(str(file_path))
                continue
            
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(url, headers=self.headers, timeout=15) as resp:
                        if resp.status == 200:
                            content = await resp.read()
                            
                            # Проверяем, что это действительно изображение
                            content_type = resp.headers.get('Content-Type', '')
                            if 'image' not in content_type and len(content) < 1000:
                                logger.warning(f"Фото {i} не является изображением, пропускаем")
                                failed += 1
                                continue
                            
                            with open(file_path, 'wb') as f:
                                f.write(content)
                            
                            downloaded += 1
                            local_paths.append(str(file_path))
                            logger.info(f"✅ Скачано фото {i}/{len(photo_urls)} ({len(content)} байт)")
                            
                            # Небольшая задержка, чтобы не блокировали
                            await asyncio.sleep(0.3)
                            
                        elif resp.status == 403:
                            logger.warning(f"⚠️ Фото {i}: доступ запрещён (403). Ozon блокирует прямой доступ.")
                            failed += 1
                        elif resp.status == 404:
                            logger.warning(f"⚠️ Фото {i}: не найдено (404). URL недействителен.")
                            failed += 1
                        else:
                            logger.warning(f"⚠️ Фото {i}: статус {resp.status}")
                            failed += 1
                            
            except asyncio.TimeoutError:
                failed += 1
                logger.error(f"❌ Таймаут при скачивании фото {i}")
            except Exception as e:
                failed += 1
                logger.error(f"❌ Ошибка при скачивании фото {i}: {e}")
        
        return {
            "downloaded": downloaded,
            "failed": failed,
            "skipped": skipped,
            "total": len(photo_urls),
            "local_paths": local_paths,
            "folder": str(product_dir)
        }


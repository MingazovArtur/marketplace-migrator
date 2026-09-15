"""
Утилиты для работы с платформами.
Единое место для функции detect_platform.
"""
from typing import Optional


def detect_platform(source_str: str) -> Optional[str]:
    """
    Определяет платформу из строки source.
    
    Args:
        source_str: Строка с названием платформы 
                    (например, "Ozon (тест)" или "Ozon → Wildberries")
    
    Returns:
        'ozon', 'wildberries', 'yandex' или None
    """
    if not source_str:
        return None
    
    s = source_str.lower()
    
    if '→' in s:
        last = s.split('→')[-1].strip()
        if 'ozon' in last:
            return 'ozon'
        if 'wildberries' in last or 'wb' in last:
            return 'wildberries'
        if 'яндекс' in last or 'yandex' in last:
            return 'yandex'
    
    if 'ozon' in s:
        return 'ozon'
    if 'wildberries' in s or 'wb' in s:
        return 'wildberries'
    if 'яндекс' in s or 'yandex' in s:
        return 'yandex'
    
    return None
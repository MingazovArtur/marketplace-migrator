"""Валидация атрибутов категории по спеку (platform_category_specs).

Вынесено без изменений из монолита services/spec_validator.py (Р12).

Правила из platform_category_specs:
- значения из словарей (регистр: warning — генератор исправит сам;
  значения нет в словаре вовсе: error — но только если атрибут в каноне)
- множественный выбор через ";" без пробелов (warning — авто-фикс)
- лимиты множественного выбора («Не более N вариантов») — у ВСЕХ атрибутов
- числа без единиц, разделитель — точка
- JSON-атрибуты (Rich-контент, Таблица размеров) — валидный JSON

Канонические атрибуты (brand/model/type/marking) проверяются ОДИН раз
в конце функции (через filled_canons) — пустой СИНОНИМ (например «Модель»
при заполненном «Объединить на одной карточке») ошибкой НЕ считается.
"""

import json
import re

from services.spec_validator._canon import (
    CANON_LABELS,
    _SYNONYM_INDEX,
    _is_canon_attr,
    _norm_name,
)

HASHTAG_RE = re.compile(r"^#[A-Za-zА-Яа-яЁё0-9_]{1,30}$")


# ==================== Атрибуты категории (спек) ====================


def _validate_attributes(product: dict, spec: dict, issues: list):
    """
    Валидация атрибутов по спеку.
    v3: агрессивная нормализация имён + канон проверяется ОДИН раз в конце.
    """
    attributes = spec.get("attributes") or []

    # ✅ Ключи product_attrs — нормализованные (без пробелов и пунктуации)
    product_attrs = {
        _norm_name(a.get("name")): (a.get("value") or "")
        for a in (product.get("attributes") or [])
        if a.get("name")
    }

    # Какие каноны уже заполнены (учитывая синонимы и нормализацию)
    filled_canons = set()
    for norm_name, val in product_attrs.items():
        canon = _SYNONYM_INDEX.get(norm_name)
        if canon and str(val).strip():
            filled_canons.add(canon)

    for attr_spec in attributes:
        name = attr_spec.get("name") or ""
        name_norm = _norm_name(name)
        value = product_attrs.get(name_norm, "")
        is_multi = attr_spec.get("type") == "multiselect"
        allowed = attr_spec.get("values") or []
        allowed_lower = {str(v).strip().lower() for v in allowed}

        canon = _is_canon_attr(name)  # None или 'brand'/'model'/'type'/'marking'
        is_spec_required = bool(attr_spec.get("required"))

        # ---------- Пустое значение ----------
        if not value.strip():
            # Канонические атрибуты (Бренд/Модель/Тип/Маркировка) проверяются ОДИН раз
            # внизу функции через filled_canons. Пустой СИНОНИМ (например «Модель» при
            # заполненном «Объединить на одной карточке») ошибкой НЕ считается.
            if not canon and is_spec_required:
                issues.append(
                    {
                        "field": f"attr:{name}",
                        "message": f"Атрибут «{name}» помечен required в API-спеке, "
                        f"но в XLS-шаблоне Ozon не обязателен — рекомендуем заполнить",
                        "severity": "warning",
                    }
                )
            continue

        # ---------- Множественный выбор: разделитель и лимит ----------
        if is_multi:
            if "; " in value or ", " in value or "," in value:
                issues.append(
                    {
                        "field": f"attr:{name}",
                        "message": f"«{name}»: значения будут приведены к формату «a;b» "
                        "(точка с запятой без пробелов) при генерации",
                        "severity": "warning",
                    }
                )
            parts = [p.strip() for p in re.split(r"[;,]", value) if p.strip()]
            max_count = attr_spec.get("max_count")
            if max_count and len(parts) > max_count:
                issues.append(
                    {
                        "field": f"attr:{name}",
                        "message": f"«{name}»: превышен лимит значений "
                        f"({len(parts)} > {max_count}) — шаблон: «Не более {max_count} вариантов»",
                        "severity": "error" if canon else "warning",
                    }
                )
        else:
            parts = [value.strip()]

        # ---------- Значения из словаря ----------
        # ---------- Значения из словаря ----------
        if allowed:
            for p in parts:
                if p in allowed:
                    continue
                if p.lower() in allowed_lower:
                    issues.append(
                        {
                            "field": f"attr:{name}",
                            "message": f"«{name}»: значение «{p}» отличается регистром от словаря — "
                            f"при генерации будет исправлено автоматически",
                            "severity": "warning",
                        }
                    )
                    continue

                # ✅ КОЛОНКА «Название модели (для объединения в одну карточку)*» в XLS-шаблоне
                # принимает СВОБОДНЫЙ текст (селлеры подставляют название товара/артикул).
                # Словарь API-атрибута «Модель» к этой колонке НЕ применяется → только warning.
                if canon == "model":
                    issues.append(
                        {
                            "field": f"attr:{name}",
                            "message": f"«{name}»: значение «{p}» не из словаря API, но колонка "
                            f"XLS-шаблона принимает свободный текст — будет записано как есть",
                            "severity": "warning",
                        }
                    )
                elif attr_spec.get("type") in ("select", "multiselect"):
                    # Словарные колонки шаблона (Бренд, Тип, Маркировка…) — значение обязано быть в словаре
                    issues.append(
                        {
                            "field": f"attr:{name}",
                            "message": f"«{name}»: значение «{p}» отсутствует в словаре площадки",
                            "severity": "error" if canon else "warning",
                        }
                    )
                else:
                    # Текстовые/числовые атрибуты со словарём-подсказкой — не блокируем
                    issues.append(
                        {
                            "field": f"attr:{name}",
                            "message": f"«{name}»: значение «{p}» не из словаря-подсказки",
                            "severity": "warning",
                        }
                    )

        # ---------- Числа ----------
        if attr_spec.get("type") == "number" and not attr_spec.get("allow_unit_in_value"):
            for p in parts:
                if re.search(r"[A-Za-zА-Яа-яЁё]", p):
                    issues.append(
                        {
                            "field": f"attr:{name}",
                            "message": f"«{name}»: число должно быть без единиц измерения (найдено: {p})",
                            "severity": "error" if canon else "warning",
                        }
                    )
                elif "," in p:
                    issues.append(
                        {
                            "field": f"attr:{name}",
                            "message": f"«{name}»: десятичный разделитель — точка (найдена запятая: {p})",
                            "severity": "warning",
                        }
                    )

        # ---------- JSON-атрибуты ----------
        if name.upper().endswith("JSON"):
            try:
                json.loads(value)
            except (ValueError, TypeError):
                issues.append(
                    {
                        "field": f"attr:{name}",
                        "message": f"«{name}»: невалидный JSON — Ozon отклонит карточку",
                        "severity": "error",
                    }
                )

        # ---------- Хештеги ----------
        if name.lower() == "#хештеги":
            tags = value.split()
            bad = [t for t in tags if not HASHTAG_RE.match(t)]
            if bad:
                issues.append(
                    {
                        "field": f"attr:{name}",
                        "message": f"Хештеги с нарушением формата: {', '.join(bad[:3])} "
                        "(нужно: #буквы_цифры, ≤30 символов)",
                        "severity": "warning",
                    }
                )
            if len(tags) > 30:
                issues.append(
                    {
                        "field": f"attr:{name}",
                        "message": f"Слишком много хештегов: {len(tags)} (максимум 30)",
                        "severity": "warning",
                    }
                )

    # ✅ Финальная проверка: все 4 канона из шаблона должны быть заполнены.
    # Это ОДИНСТВЕННОЕ место, где канон даёт error — защита от двойных ошибок.
    for canon, label in CANON_LABELS.items():
        if canon not in filled_canons:
            issues.append(
                {
                    "field": f"attr:{canon}",
                    "message": f"Обязательный атрибут «{label}»* не заполнен (требуется XLS-шаблоном Ozon)",
                    "severity": "error",
                }
            )

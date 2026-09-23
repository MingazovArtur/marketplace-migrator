"""
Нормализатор атрибутов товара по спекам площадок.

При сохранении атрибутов подбирает значение с правильным регистром
из словаря площадки (Ozon чувствителен к регистру — «белый» ≠ «Белый»).

Возвращает:
- normalized_attributes: список атрибутов с нормализованными значениями
- normalizations: список фактов нормализации (для UI-уведомлений)
- warnings: значения, которых нет в словаре площадки
"""
import re
from typing import Optional


def normalize_attributes(
    attributes: list,
    spec: Optional[dict],
) -> dict:
    """
    Нормализует список атрибутов товара по спеку категории.

    Args:
        attributes: список {"name": str, "value": str, ...}
        spec: спек категории (из PlatformCategorySpec.spec) или None

    Returns:
        {
            "normalized_attributes": list,   # атрибуты с нормализованными значениями
            "normalizations": list,          # что было нормализовано
            "warnings": list,                # значения не из словаря
        }
    """
    if not spec:
        return {
            "normalized_attributes": attributes,
            "normalizations": [],
            "warnings": [],
        }

    spec_attrs = {
        (a.get("name") or "").strip().lower(): a
        for a in (spec.get("attributes") or [])
    }

    normalized = []
    normalizations = []
    warnings = []

    for attr in attributes:
        attr_name = (attr.get("name") or "").strip()
        attr_value = attr.get("value") or ""
        spec_attr = spec_attrs.get(attr_name.lower())

        new_value = attr_value
        normalized_flag = False
        warning = None

        if spec_attr and attr_value:
            allowed_values = spec_attr.get("values") or []

            if allowed_values:
                attr_type = spec_attr.get("type", "text")
                separator = spec_attr.get("separator", ";")

                if attr_type == "multiselect":
                    # Множественный выбор: нормализуем каждое значение
                    parts = re.split(rf"\s*{re.escape(separator)}\s*", attr_value)
                    new_parts = []
                    for part in parts:
                        if not part.strip():
                            continue
                        matched = _match_case(part.strip(), allowed_values)
                        if matched and matched != part:
                            normalizations.append({
                                "field": attr_name,
                                "original": part,
                                "normalized": matched,
                            })
                            normalized_flag = True
                        if matched is None:
                            warnings.append({
                                "field": attr_name,
                                "value": part,
                                "message": f"Значение «{part}» отсутствует в словаре площадки",
                            })
                        new_parts.append(matched or part)
                    new_value = separator.join(new_parts)

                else:
                    # Одиночный выбор
                    matched = _match_case(attr_value, allowed_values)
                    if matched and matched != attr_value:
                        normalizations.append({
                            "field": attr_name,
                            "original": attr_value,
                            "normalized": matched,
                        })
                        new_value = matched
                        normalized_flag = True
                    elif matched is None:
                        warnings.append({
                            "field": attr_name,
                            "value": attr_value,
                            "message": f"Значение «{attr_value}» отсутствует в словаре площадки",
                        })

        new_attr = {**attr, "value": new_value}
        normalized.append(new_attr)

    return {
        "normalized_attributes": normalized,
        "normalizations": normalizations,
        "warnings": warnings,
    }


def _match_case(value: str, allowed_values: list) -> Optional[str]:
    """Подбирает значение из словаря с точным совпадением (case-insensitive)."""
    low = value.strip().lower()
    for v in allowed_values:
        if str(v).strip().lower() == low:
            return str(v)
    return None
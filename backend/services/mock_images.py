from PIL import Image, ImageDraw, ImageFont
from pathlib import Path
import io

def create_mock_image(product_name: str, index: int = 1) -> bytes:
    """
    Создаёт тестовое изображение с текстом (заглушка для Mock-режима)
    Требует: pip install pillow
    """
    # Создаём изображение 800x800
    img = Image.new('RGB', (800, 800), color='#f0f0f0')
    draw = ImageDraw.Draw(img)
    
    # Рисуем рамку
    draw.rectangle([10, 10, 790, 790], outline='#4f46e5', width=3)
    
    # Добавляем текст
    try:
        font = ImageFont.truetype("arial.ttf", 30)
    except:
        font = ImageFont.load_default()
    
    # Название товара (переносим на новую строку если длинное)
    words = product_name.split()
    lines = []
    current_line = ""
    for word in words:
        if len(current_line + word) < 40:
            current_line += word + " "
        else:
            lines.append(current_line.strip())
            current_line = word + " "
    lines.append(current_line.strip())
    
    # Рисуем текст по центру
    y_position = 350
    for line in lines[:5]:  # Максимум 5 строк
        text_width = draw.textlength(line, font=font)
        draw.text((400 - text_width/2, y_position), line, fill='#333333', font=font)
        y_position += 50
    
    # Добавляем номер фото
    draw.text((400, 600), f"Фото #{index}", fill='#666666', font=font, anchor="mm")
    draw.text((400, 650), "(Mock)", fill='#999999', font=font, anchor="mm")
    
    # Сохраняем в bytes
    img_bytes = io.BytesIO()
    img.save(img_bytes, format='JPEG', quality=85)
    img_bytes.seek(0)
    
    return img_bytes.read()
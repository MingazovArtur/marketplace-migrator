"""
Обрезает пустые поля у иконок и приводит к квадрату 512x512 (фон сохраняется).
После прогона в Icon поставьте zoom = 1.
Запуск (одноразово):
  docker run --rm -v ${PWD}:/work -w /work python:3.12-slim sh -c "pip install -q pillow && python tools/preprocess_icons.py"
"""
from pathlib import Path
from PIL import Image, ImageChops

ICONS_DIR = Path("frontend/src/assets/icons")
SIZE = 512
PAD = 0.06   # небольшой отступ вокруг глифа


def autocrop_square(path: Path) -> None:
    im = Image.open(path).convert("RGB")
    im.thumbnail((1024, 1024), Image.LANCZOS)          # ускоряем обработку

    bg = Image.new("RGB", im.size, im.getpixel((2, 2)))
    diff = ImageChops.difference(im, bg).convert("L")
    mask = diff.point(lambda p: 255 if p > 24 else 0)
    bbox = mask.getbbox()
    if bbox:
        im = im.crop(bbox)

    w, h = im.size
    side = int(max(w, h) * (1 + PAD * 2))
    canvas = Image.new("RGB", (side, side), im.getpixel((0, 0)))
    canvas.paste(im, ((side - w) // 2, (side - h) // 2))

    canvas.resize((SIZE, SIZE), Image.LANCZOS).save(path, "PNG")
    print(f"✅ {path.name} -> {SIZE}x{SIZE}")


if __name__ == "__main__":
    for p in sorted(ICONS_DIR.glob("*.png")):
        try:
            autocrop_square(p)
        except Exception as e:
            print(f"⚠️ {p.name}: {e}")
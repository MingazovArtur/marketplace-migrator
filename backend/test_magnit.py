import os
import sys

# Убедимся, что путь к приложению в sys.path
sys.path.insert(0, "/app")

from parsers.file_parser import parse_file

# Путь к файлу внутри контейнера (убедитесь, что файл туда попал)
FILE_PATH = "/app/data/magnit_sample.xlsx"

if not os.path.exists(FILE_PATH):
    print(f"[!] Файл {FILE_PATH} не найден внутри контейнера.")
    print(
        "Проверьте, смонтирована ли папка data в docker-compose.yml или скопируйте файл командой:"
    )
    print("docker compose cp ./magnit_sample.xlsx backend:/app/data/")
    sys.exit(1)

print(f"Читаем файл: {FILE_PATH}\n" + "-" * 40)

with open(FILE_PATH, "rb") as f:
    content = f.read()

try:
    # Запускаем парсер
    result = parse_file(content, "magnit", "xlsx")

    print(f"Всего строк в файле: {result.get('total_rows', 0)}")
    print(f"Распознано карточек: {len(result.get('products', []))}")
    print(f"Ошибок валидации: {len(result.get('errors', []))}")
    print(f"Предупреждений: {len(result.get('warnings', []))}\n")

    print("Первые 5 карточек:")
    for p in result.get("products", [])[:5]:
        print(f"  - {p.get('name', '')[:50]}")
        print(
            f"    SKU: {p.get('sku','—')} | Product ID: {p.get('external_id','—')} | SKU в карточке: {p.get('sku_count',1)}"
        )
        print(
            f"    Бренд: {p.get('brand','—')} | Фото: {len(p.get('photos',[]))} | Описание: {len(p.get('description',''))} симв."
        )

    if result.get("errors"):
        print("\nПервые 5 ошибок:")
        for e in result.get("errors", [])[:5]:
            print(f"  - {e}")

except Exception as e:
    print(f"Критическая ошибка при парсинге: {e}")
    import traceback

    traceback.print_exc()

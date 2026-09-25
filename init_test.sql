-- init_test.sql
INSERT INTO products (
    user_id, source, sku, name, price, category,
    photos, description, status, created_at, updated_at
) VALUES (
    1,
    'Магнит Маркет (Файл)',
    'TSH-001',
    'Футболка для девочек',
    990,
    'Одежда для малышей',
    '["https://ke-images.servicecdn.ru/test/tshirt.jpg"]'::jsonb,
    'Тестовая футболка для девочек, хлопок 100%',
    'pending',
    NOW(),
    NOW()
) RETURNING id;
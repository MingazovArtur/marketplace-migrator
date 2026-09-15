"""
Скрипт для создания первого администратора
Запуск: docker compose exec backend python scripts/create_admin.py
"""
import sys
import os

# Добавляем путь к проекту
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.session import SessionLocal
from database.models import User
from core.auth import get_password_hash


def create_admin(email: str, username: str, password: str):
    """Создаёт пользователя с ролью admin"""
    db = SessionLocal()
    try:
        # Проверяем, существует ли пользователь
        existing_user = db.query(User).filter(User.username == username).first()
        if existing_user:
            print(f"❌ Пользователь '{username}' уже существует")
            return False
        
        # Создаём администратора
        admin = User(
            email=email,
            username=username,
            hashed_password=get_password_hash(password),
            role="admin",
            is_active=True
        )
        db.add(admin)
        db.commit()
        db.refresh(admin)
        
        print(f"✅ Администратор создан успешно!")
        print(f"   Email: {email}")
        print(f"   Username: {username}")
        print(f"   Role: admin")
        return True
        
    except Exception as e:
        db.rollback()
        print(f"❌ Ошибка: {e}")
        return False
    finally:
        db.close()


if __name__ == "__main__":
    if len(sys.argv) != 4:
        print("Использование: python create_admin.py <email> <username> <password>")
        print("Пример: python create_admin.py admin@example.com admin admin123")
        sys.exit(1)
    
    email = sys.argv[1]
    username = sys.argv[2]
    password = sys.argv[3]
    
    create_admin(email, username, password)
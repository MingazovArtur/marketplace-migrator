from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from core.config import BASE_DIR

# Используем SQLite для простоты разработки. 
# Для перехода на PostgreSQL достаточно заменить эту строку на:
# "postgresql://user:password@localhost/dbname"
SQLALCHEMY_DATABASE_URL = f"sqlite:///{BASE_DIR}/migrator.db"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
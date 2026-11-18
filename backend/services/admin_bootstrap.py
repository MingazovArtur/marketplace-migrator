"""Стартовый админ из переменных окружения.

ADMIN_USERNAME / ADMIN_EMAIL / ADMIN_PASSWORD в .env — и при старте
приложения создаётся администратор, если его ещё нет. Решает проблему
«свежий прод, а админа можно завести только SQL'ем».

Идемпотентно и безопасно:
- пользователь с таким username уже есть → ничего не делаем (пароль и
  роль НЕ перезаписываем — иначе регистрация чужим именем до старта
  отдаст злоумышленнику админку);
- пароль-заглушка (CHANGE_ME…) → пропускаем с предупреждением;
- БД недоступна → предупреждение в лог, приложение продолжает работать
  (бутстрап не должен ронять старт).
"""

import logging

from core.time import utcnow

logger = logging.getLogger(__name__)


def bootstrap_initial_admin() -> None:
    """Создать стартового админа из настроек, если задан и ещё не существует."""
    try:
        from core.auth import get_password_hash
        from core.config import settings
        from database.models import User
        from database.session import SessionLocal

        username = (settings.ADMIN_USERNAME or "").strip()
        email = (settings.ADMIN_EMAIL or "").strip()
        password = settings.ADMIN_PASSWORD or ""

        if not (username and email and password):
            return
        if password.startswith("CHANGE_ME"):
            logger.warning("ADMIN_PASSWORD похож на заглушку — бутстрап админа пропущен")
            return

        with SessionLocal() as db:
            existing = db.query(User).filter(User.username == username).first()
            if existing is not None:
                if existing.role != "admin":
                    logger.warning(
                        f"ADMIN_USERNAME='{username}' уже занят пользователем без роли "
                        "admin — бутстрап пропущен (роль не перезаписываем)"
                    )
                return

            user = User(
                email=email,
                username=username,
                hashed_password=get_password_hash(password),
                role="admin",
                is_active=True,
                email_verified_at=utcnow(),
            )
            db.add(user)
            db.commit()
            logger.info(f"Создан стартовый админ '{username}' (id={user.id})")
    except Exception as e:
        logger.warning(f"Бутстрап стартового админа не выполнен ({e}) — создайте админа вручную")

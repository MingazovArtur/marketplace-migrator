#!/usr/bin/env bash
# ============================================================
# Настройка HTTPS одной командой.
#
# КОГДА запускать: после покупки домена и создания A-записи,
# указывающей на этот сервер (***REMOVED***), у регистратора.
#
# КАК (на проде, из корня проекта):
#   bash deploy/https/setup-https.sh vashdomen.ru admin@vashdomen.ru
#
# ЧТО делает:
#   1. Показывает, куда резолвится домен (сверьте с IP сервера)
#   2. Выпускает сертификат Let's Encrypt через уже работающий
#      nginx :80 (webroot-челлендж, объём webroot общий с certbot)
#   3. Подставляет домен в шаблон deploy/nginx/https.conf.disabled
#      и кладёт результат в deploy/nginx/conf.d/https.conf
#   4. Проверяет конфиг (nginx -t) и плавно перезагружает nginx
#      (reload — без разрыва соединений, простой нулевой)
#
# Откат: rm deploy/nginx/conf.d/https.conf && перезагрузить nginx.
# ============================================================
set -euo pipefail

# Корень проекта (где docker-compose.prod.yml) — на случай запуска из другого cwd
cd "$(dirname "$0")/../.."

DOMAIN="${1:?Использование: bash deploy/https/setup-https.sh <домен> <email>}"
EMAIL="${2:?Использование: bash deploy/https/setup-https.sh <домен> <email>}"

COMPOSE="docker compose -f docker-compose.prod.yml"

echo "==> 1/4 Проверка DNS"
RESOLVED="$(getent hosts "$DOMAIN" 2>/dev/null | awk '{print $1}' | head -1 || true)"
if [ -n "$RESOLVED" ]; then
    echo "    $DOMAIN резолвится в: $RESOLVED"
    echo "    (должно совпадать с публичным IP этого сервера; проверьте, если нет)"
else
    echo "    ВНИМАНИЕ: $DOMAIN пока НЕ резолвится."
    echo "    Создайте у регистратора A-запись: $DOMAIN -> <IP сервера> и подождите 5-30 минут."
    read -r -p "    Продолжить всё равно? [y/N] " ANSWER
    case "$ANSWER" in
        [yY]*) ;;
        *) echo "Остановлено."; exit 1 ;;
    esac
fi

echo "==> 2/4 Выпуск сертификата Let's Encrypt (webroot через работающий nginx)"
# exec в уже работающий контейнер certbot (тома certs и webroot совпадают с nginx).
# -T: без TTY — скрипт можно звать из cron/CI. Все флаги => certbot не задаст вопросов.
$COMPOSE exec -T certbot \
    certbot certonly --webroot -w /var/www/certbot -d "$DOMAIN" \
    --email "$EMAIL" --agree-tos --no-eff-email --keep-until-expiring

echo "==> 3/4 Установка конфига nginx (443 + редирект)"
sed "s/__DOMAIN__/$DOMAIN/g" deploy/nginx/https.conf.disabled \
    > deploy/nginx/conf.d/https.conf

echo "==> 4/4 Проверка и плавная перезагрузка nginx"
$COMPOSE exec -T nginx nginx -t
$COMPOSE exec -T nginx nginx -s reload

echo
echo "Готово. Проверка:"
echo "  curl -fI  http://$DOMAIN/api/health   # ожидаем: 301"
echo "  curl -f  https://$DOMAIN/api/health   # ожидаем: 200 OK"
echo
echo "Важно (продление): certbot обновляет сертификат сам каждые 12 часов,"
echo "но nginx подхватывает новый файл только после reload. Добавьте в crontab"
echo "хоста (crontab -e) строку:"
echo "  @daily docker exec marketplace-prod-nginx-1 nginx -s reload"
echo "(reload бесплатный и безопасный — просто перечитывает конфиг и сертификаты)"

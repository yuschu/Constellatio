#!/bin/sh
# Constellatio 容器启动脚本：迁移 → 静态收集 → 初始超管 → gunicorn
set -e

echo "[entrypoint] migrate"
python manage.py migrate --noinput

echo "[entrypoint] collectstatic"
python manage.py collectstatic --noinput

# 首次启动创建初始超管（环境变量可控，幂等）
if [ -n "$DJANGO_SUPERUSER_USERNAME" ] && [ -n "$DJANGO_SUPERUSER_PASSWORD" ]; then
  echo "[entrypoint] ensure superuser $DJANGO_SUPERUSER_USERNAME"
  python manage.py shell -c "
from plugins.user.models import User
if not User.objects.filter(username='$DJANGO_SUPERUSER_USERNAME').exists():
    User.objects.create_superuser('$DJANGO_SUPERUSER_USERNAME', '', '$DJANGO_SUPERUSER_PASSWORD')
    print('superuser created')
else:
    print('superuser exists')
"
fi

echo "[entrypoint] gunicorn"
exec gunicorn plugin_host.wsgi:application \
    --bind 0.0.0.0:8000 \
    --workers "${GUNICORN_WORKERS:-3}" \
    --access-logfile - \
    --error-logfile -

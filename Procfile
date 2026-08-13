release: flask db upgrade
web: gunicorn wsgi:app --workers ${WEB_CONCURRENCY:-3} --timeout 30 --access-logfile - --error-logfile -

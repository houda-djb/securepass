FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /srv/app

# The app never runs as root: if it is ever compromised, it can change very little.
RUN useradd --system --uid 10001 --home-dir /srv/app appuser

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY --chown=appuser:appuser . .
# Windows editors may save the script with CRLF line endings, which the container can't run.
RUN sed -i 's/\r$//' docker-entrypoint.sh

USER appuser

ENV FLASK_ENV=production \
    PORT=8000
EXPOSE 8000

CMD ["sh", "docker-entrypoint.sh"]

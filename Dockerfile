FROM python:3.12-slim

# Unbuffered output so logs appear in Code Engine log viewer
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install deps first (layer caching — code changes don't re-install)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy app code only (not .env, .git, etc — see .dockerignore)
COPY app/ app/

# Non-root user
RUN adduser --disabled-password --no-create-home appuser
USER appuser

# Code Engine injects PORT (default 8080)
EXPOSE 8080
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080}

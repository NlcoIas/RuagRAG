FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY redundancy_check.py .
EXPOSE 8080
CMD ["uvicorn", "redundancy_check:app", "--host", "0.0.0.0", "--port", "8080"]
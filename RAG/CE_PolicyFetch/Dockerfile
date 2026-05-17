FROM python:3.11-slim
WORKDIR /app
RUN pip install fastapi uvicorn requests httpx
COPY policy_fetch.py .
CMD ["uvicorn", "policy_fetch:app", "--host", "0.0.0.0", "--port", "8080"]

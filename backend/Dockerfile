FROM python:3.13-slim
WORKDIR /app
ARG APP_VERSION=1.0.0
ENV APP_VERSION=$APP_VERSION
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && useradd --uid 10001 --create-home app
COPY main.py .
USER 10001
EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--timeout-graceful-shutdown", "45"]

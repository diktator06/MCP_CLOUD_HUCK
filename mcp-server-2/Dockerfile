# MCP Server 2: GitHub Repository Comparison Utility
FROM python:3.12-slim

# Установка рабочей директории
WORKDIR /app

# Установка системных зависимостей
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Копирование файлов проекта
COPY pyproject.toml ./
COPY mcp_instance.py ./
COPY server.py ./
COPY metrics.py ./
COPY env_options.json ./
COPY mcp-server-catalog.yaml ./
COPY mcp_tools.json ./
COPY tools/ ./tools/

# Установка зависимостей Python
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir fastmcp>=2.0.0 httpx>=0.27.0 pydantic>=2.0.0 python-dotenv>=1.0.0 opentelemetry-api>=1.20.0 opentelemetry-sdk>=1.20.0 aiolimiter>=1.1.0 prometheus-client>=0.19.0

# Переменные окружения по умолчанию
ENV PORT=8001
ENV HOST=0.0.0.0
ENV PYTHONUNBUFFERED=1

# Открытие порта
EXPOSE 8001

# Команда запуска
CMD ["python", "server.py"]


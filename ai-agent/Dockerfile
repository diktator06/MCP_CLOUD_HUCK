# AI Agent: LangChain Agent with Evolution Foundation Models
FROM python:3.12-slim

# Установка рабочей директории
WORKDIR /app

# Установка системных зависимостей
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Копирование файлов проекта
COPY pyproject.toml ./
COPY src/ ./src/
COPY schemas.py ./

# Установка зависимостей Python
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir langchain==0.3.0 langchain-openai==0.2.0 httpx>=0.27.0 pydantic>=2.0.0 python-dotenv>=1.0.0 fastapi>=0.104.0 "uvicorn[standard]>=0.24.0"

# Переменные окружения по умолчанию
ENV PYTHONUNBUFFERED=1

# Команда запуска
# По умолчанию запускаем API сервер
# Для интерактивного режима используйте: python src/start_a2a.py
CMD ["python", "src/api_server.py"]


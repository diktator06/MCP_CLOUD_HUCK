"""MCP сервер для анализа релизов и тегов репозиториев GitHub."""

# Standard library
import os
from typing import Dict, Any

# Third-party
from dotenv import load_dotenv, find_dotenv

# Load environment variables
load_dotenv(find_dotenv())

from fastmcp import FastMCP, Context
from opentelemetry import trace

# Импортируем единый экземпляр FastMCP
from mcp_instance import mcp
from metrics import start_metrics_server

# Константы
PORT = int(os.getenv("PORT", "8005"))
HOST = os.getenv("HOST", "0.0.0.0")

# OpenTelemetry tracer
tracer = trace.get_tracer(__name__)


# Инициализация трейсинга
def init_tracing():
    """Инициализация OpenTelemetry для трейсинга."""
    pass


init_tracing()

# Импортируем инструменты
from tools.releases_summary import get_releases_summary
from tools.tags_analysis import analyze_repository_tags
from tools.version_comparison import compare_release_versions


def main():
    """Запуск MCP сервера с HTTP транспортом."""
    print("=" * 60)
    print("🌐 ЗАПУСК MCP СЕРВЕРА")
    print("=" * 60)
    print(f"🚀 MCP Server: http://{HOST}:{PORT}/mcp")
    print(f"📊 Сервер: GitHub Releases & Tags")
    print(f"🔧 Инструменты:")
    print(f"   - get_releases_summary")
    print(f"   - analyze_repository_tags")
    print(f"   - compare_release_versions")
    print(f"📊 Prometheus metrics: http://{HOST}:{PORT + 1000}/metrics")
    print("=" * 60)
    
    # Запускаем Prometheus metrics server
    start_metrics_server()
    
    # Запускаем MCP сервер с streamable-http транспортом
    mcp.run(
        transport="streamable-http",
        host=HOST,
        port=PORT,
        stateless_http=True
    )


if __name__ == "__main__":
    main()


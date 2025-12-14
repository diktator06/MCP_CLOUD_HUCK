"""
Structured logging utility для всех сервисов.
Обеспечивает единый формат JSON логов для мониторинга и отладки.
"""

import json
import logging
import sys
from datetime import datetime
from typing import Optional, Dict, Any
from enum import Enum


class LogLevel(str, Enum):
    """Уровни логирования."""
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class StructuredLogger:
    """
    Structured logger с JSON форматом вывода.
    
    Пример использования:
        logger = StructuredLogger("ai-agent")
        logger.info("Agent initialized", extra={"model": "Qwen/Qwen3-Next-80B"})
    """
    
    def __init__(self, service_name: str, level: LogLevel = LogLevel.INFO):
        """
        Инициализация structured logger.
        
        Args:
            service_name: Имя сервиса (например, "ai-agent", "mcp-server-1")
            level: Уровень логирования
        """
        self.service_name = service_name
        self.logger = logging.getLogger(service_name)
        self.logger.setLevel(getattr(logging, level.value))
        
        # Удаляем существующие handlers
        self.logger.handlers = []
        
        # Создаем JSON formatter handler
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(JSONFormatter(service_name))
        self.logger.addHandler(handler)
    
    def _log(self, level: str, message: str, **kwargs):
        """Внутренний метод для логирования."""
        extra = {
            "service": self.service_name,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            **kwargs
        }
        getattr(self.logger, level.lower())(message, extra=extra)
    
    def debug(self, message: str, **kwargs):
        """Логирование уровня DEBUG."""
        self._log("DEBUG", message, **kwargs)
    
    def info(self, message: str, **kwargs):
        """Логирование уровня INFO."""
        self._log("INFO", message, **kwargs)
    
    def warning(self, message: str, **kwargs):
        """Логирование уровня WARNING."""
        self._log("WARNING", message, **kwargs)
    
    def error(self, message: str, **kwargs):
        """Логирование уровня ERROR."""
        self._log("ERROR", message, **kwargs)
    
    def critical(self, message: str, **kwargs):
        """Логирование уровня CRITICAL."""
        self._log("CRITICAL", message, **kwargs)


class JSONFormatter(logging.Formatter):
    """JSON formatter для structured logging."""
    
    def __init__(self, service_name: str):
        super().__init__()
        self.service_name = service_name
    
    def format(self, record: logging.LogRecord) -> str:
        """Форматирует запись лога в JSON."""
        # Получаем extra данные, если они есть
        extra_data = getattr(record, 'extra', {})
        
        log_data = {
            "timestamp": extra_data.get("timestamp", datetime.utcnow().isoformat() + "Z"),
            "level": record.levelname,
            "service": extra_data.get("service", self.service_name),
            "message": record.getMessage(),
        }
        
        # Добавляем дополнительные поля из extra
        for key, value in extra_data.items():
            if key not in ["timestamp", "service"]:
                log_data[key] = value
        
        # Добавляем информацию об исключении, если есть
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)
        
        return json.dumps(log_data, ensure_ascii=False)


# Глобальный экземпляр для AI Agent
_ai_agent_logger: Optional[StructuredLogger] = None


def get_logger(service_name: str = "ai-agent", level: LogLevel = LogLevel.INFO) -> StructuredLogger:
    """
    Получить или создать structured logger для сервиса.
    
    Args:
        service_name: Имя сервиса
        level: Уровень логирования
        
    Returns:
        StructuredLogger экземпляр
    """
    global _ai_agent_logger
    if service_name == "ai-agent" and _ai_agent_logger is None:
        _ai_agent_logger = StructuredLogger(service_name, level)
    elif service_name != "ai-agent":
        return StructuredLogger(service_name, level)
    return _ai_agent_logger


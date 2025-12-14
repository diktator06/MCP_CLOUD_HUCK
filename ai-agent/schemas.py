"""Pydantic схемы для валидации входных и выходных данных инструментов."""

from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime


# ============================================================================
# Input Schemas (для параметров инструментов)
# ============================================================================

class RepositoryIdentifier(BaseModel):
    """Идентификатор репозитория GitHub."""
    
    owner: str = Field(
        ...,
        description="Владелец репозитория (username или organization name)"
    )
    repo: str = Field(
        ...,
        description="Название репозитория"
    )


class GetRepositoryHealthInput(BaseModel):
    """Входные параметры для получения метрик здоровья репозитория."""
    
    owner: str = Field(
        ...,
        description="Владелец репозитория (username или organization name)",
        examples=["octocat", "microsoft"]
    )
    repo: str = Field(
        ...,
        description="Название репозитория",
        examples=["Hello-World", "vscode"]
    )


class GetRepositoryIssuesSummaryInput(BaseModel):
    """Входные параметры для получения сводки по issues репозитория."""
    
    owner: str = Field(
        ...,
        description="Владелец репозитория (username или organization name)",
        examples=["octocat", "microsoft"]
    )
    repo: str = Field(
        ...,
        description="Название репозитория",
        examples=["Hello-World", "vscode"]
    )
    state: Optional[str] = Field(
        default="open",
        description="Статус issues: 'open', 'closed', или 'all'",
        examples=["open", "closed", "all"]
    )
    labels: Optional[List[str]] = Field(
        default=None,
        description="Список labels для фильтрации issues",
        examples=[["bug", "enhancement"]]
    )


class CompareRepositoriesInput(BaseModel):
    """Входные параметры для сравнения нескольких репозиториев."""
    
    repositories: List[Dict[str, str]] = Field(
        ...,
        description="Список репозиториев для сравнения. Каждый элемент должен содержать 'owner' и 'repo'",
        min_items=2,
        max_items=5,
        examples=[
            [
                {"owner": "octocat", "repo": "Hello-World"},
                {"owner": "microsoft", "repo": "vscode"}
            ]
        ]
    )
    metrics: Optional[List[str]] = Field(
        default=None,
        description="Список метрик для сравнения. Если не указан, сравниваются все доступные метрики",
        examples=[["open_issues", "open_prs", "last_commit_age"]]
    )


# ============================================================================
# Output Schemas (для структурированных ответов)
# ============================================================================

class RepositoryHealthMetrics(BaseModel):
    """Метрики здоровья репозитория."""
    
    owner: str = Field(..., description="Владелец репозитория")
    repo: str = Field(..., description="Название репозитория")
    open_issues_count: int = Field(..., description="Количество открытых issues")
    open_prs_count: int = Field(..., description="Количество открытых pull requests")
    last_commit_date: Optional[datetime] = Field(None, description="Дата последнего коммита")
    last_commit_age_days: Optional[int] = Field(None, description="Возраст последнего коммита в днях")
    stars_count: int = Field(..., description="Количество звезд")
    forks_count: int = Field(..., description="Количество форков")
    watchers_count: int = Field(..., description="Количество наблюдателей")
    is_archived: bool = Field(..., description="Архивирован ли репозиторий")
    is_disabled: bool = Field(..., description="Отключен ли репозиторий")
    default_branch: str = Field(..., description="Ветка по умолчанию")
    language: Optional[str] = Field(None, description="Основной язык программирования")
    created_at: datetime = Field(..., description="Дата создания репозитория")
    updated_at: datetime = Field(..., description="Дата последнего обновления")
    pushed_at: Optional[datetime] = Field(None, description="Дата последнего push")


class IssueSummary(BaseModel):
    """Сводка по issue."""
    
    number: int = Field(..., description="Номер issue")
    title: str = Field(..., description="Заголовок issue")
    state: str = Field(..., description="Статус: 'open' или 'closed'")
    labels: List[str] = Field(default_factory=list, description="Список labels")
    created_at: datetime = Field(..., description="Дата создания")
    updated_at: datetime = Field(..., description="Дата последнего обновления")
    comments_count: int = Field(..., description="Количество комментариев")
    assignees_count: int = Field(..., description="Количество назначенных исполнителей")


class RepositoryIssuesSummary(BaseModel):
    """Сводка по issues репозитория."""
    
    owner: str = Field(..., description="Владелец репозитория")
    repo: str = Field(..., description="Название репозитория")
    total_issues: int = Field(..., description="Общее количество issues")
    open_issues: int = Field(..., description="Количество открытых issues")
    closed_issues: int = Field(..., description="Количество закрытых issues")
    issues_by_label: Dict[str, int] = Field(
        default_factory=dict,
        description="Количество issues по каждому label"
    )
    issues_by_priority: Dict[str, int] = Field(
        default_factory=dict,
        description="Количество issues по приоритетам (если определены)"
    )
    recent_issues: List[IssueSummary] = Field(
        default_factory=list,
        description="Список последних issues (максимум 10)"
    )


class RepositoryComparison(BaseModel):
    """Сравнение метрик репозиториев."""
    
    repositories: List[Dict[str, str]] = Field(..., description="Список сравниваемых репозиториев")
    comparison_date: datetime = Field(..., description="Дата сравнения")
    metrics: Dict[str, Dict[str, Any]] = Field(
        ...,
        description="Сравнение метрик. Ключ - название метрики, значение - словарь с данными по каждому репозиторию"
    )
    summary: Dict[str, Any] = Field(
        ...,
        description="Сводка сравнения с выявлением лидеров по различным метрикам"
    )


# ============================================================================
# Error Schemas
# ============================================================================

class APIError(BaseModel):
    """Схема ошибки API."""
    
    error_code: str = Field(..., description="Код ошибки")
    error_message: str = Field(..., description="Сообщение об ошибке")
    status_code: Optional[int] = Field(None, description="HTTP статус код")
    details: Optional[Dict[str, Any]] = Field(None, description="Дополнительные детали ошибки")


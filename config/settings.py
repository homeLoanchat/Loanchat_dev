"""FastAPI 및 서비스 전역 설정 모듈."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import List

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """환경 변수 기반 애플리케이션 설정."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    env: str = Field(default="local", alias="ENV", description="실행 환경 식별자")
    port: int = Field(default=8000, alias="PORT", description="FastAPI 서비스 포트")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL", description="루트 로그 레벨")
    allowed_origins: str = Field(
        default="*",
        alias="LOANBOT_ALLOWED_ORIGINS",
        description="CORS 허용 origin (쉼표 구분)",
    )

    vectorstore_path: Path | None = Field(
        default=None,
        alias="VECTORSTORE_PATH",
        description="벡터스토어 퍼시스턴스 디렉터리",
    )
    websearch_api_key: SecretStr | None = Field(
        default=None,
        alias="WEBSEARCH_API_KEY",
        description="외부 웹 검색 API 키",
    )
    admin_secret: SecretStr = Field(
        alias="ADMIN_SECRET",
        description="관리자 API 접근 토큰",
    )
    metrics_window: int = Field(
        default=1000,
        alias="METRICS_WINDOW",
        description="레이턴시 히스토리 최대 길이",
    )

    @property
    def allowed_origins_list(self) -> list[str]:
        values: list[str] = [origin.strip() for origin in self.allowed_origins.split(",") if origin.strip()]
        return values or ["*"]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """싱글톤 설정 인스턴스를 반환한다."""

    return Settings()


__all__ = ["Settings", "get_settings"]

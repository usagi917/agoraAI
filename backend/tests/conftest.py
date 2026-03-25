"""共通テストフィクスチャ"""

import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy.ext.asyncio import (
    create_async_engine,
    AsyncSession,
    async_sessionmaker,
)
from src.app.database import Base


@pytest_asyncio.fixture
async def db_session():
    """テスト用のインメモリ SQLite セッション"""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    async with session_factory() as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture
def mock_sse_manager():
    """SSE マネージャーのモック"""
    with patch("src.app.sse.manager.sse_manager") as mock:
        mock.publish = AsyncMock()
        mock.add_alias = MagicMock()
        mock.remove_alias = MagicMock()
        yield mock


@pytest.fixture
def mock_llm_client():
    """LLM クライアントのモック"""
    with patch("src.app.llm.client.LLMClient") as mock_cls:
        mock = MagicMock()
        mock.call = AsyncMock(
            return_value=({"result": "test"}, {"total_tokens": 10})
        )
        mock.call_with_retry = AsyncMock(
            return_value=({"result": "test"}, {"total_tokens": 10})
        )
        mock.call_batch = AsyncMock(return_value=[])
        mock_cls.return_value = mock
        yield mock

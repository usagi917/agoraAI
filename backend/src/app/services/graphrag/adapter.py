"""GraphRAG アダプター: パイプライン実装を差し替え可能にする抽象レイヤー"""

from abc import ABC, abstractmethod

from sqlalchemy.ext.asyncio import AsyncSession

from src.app.config import settings
from src.app.services.graphrag.pipeline import GraphRAGPipeline, KnowledgeGraph


class GraphRAGAdapter(ABC):
    """GraphRAG パイプラインの抽象基底クラス。

    実装を差し替えることで、異なるKG構築エンジン（自作, LightRAG 等）を
    ベンチマーク比較できる。
    """

    name: str

    @abstractmethod
    async def build_knowledge_graph(
        self,
        session: AsyncSession,
        run_id: str,
        document_text: str,
        theme: str = "",
    ) -> KnowledgeGraph:
        """ドキュメントからナレッジグラフを構築する。"""


class BuiltinAdapter(GraphRAGAdapter):
    """既存の GraphRAGPipeline をラップするアダプター。"""

    name = "builtin"

    def __init__(self) -> None:
        self._pipeline = GraphRAGPipeline()

    async def build_knowledge_graph(
        self,
        session: AsyncSession,
        run_id: str,
        document_text: str,
        theme: str = "",
    ) -> KnowledgeGraph:
        return await self._pipeline.run(
            session, run_id, document_text, theme=theme,
        )


_ADAPTERS: dict[str, type[GraphRAGAdapter]] = {
    "builtin": BuiltinAdapter,
}


def create_adapter(name: str | None = None) -> GraphRAGAdapter:
    """設定またはname引数に基づいてアダプターを生成する。"""
    if name is None:
        config = settings.load_graphrag_config()
        name = config.get("adapter", "builtin")

    adapter_cls = _ADAPTERS.get(name)
    if adapter_cls is None:
        raise ValueError(f"Unknown GraphRAG adapter: {name}. Available: {list(_ADAPTERS.keys())}")

    return adapter_cls()

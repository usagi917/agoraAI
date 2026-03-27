"""GraphRAG アダプターパターンのテスト"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock


class TestGraphRAGAdapterABC:
    def test_is_abstract(self):
        from src.app.services.graphrag.adapter import GraphRAGAdapter
        with pytest.raises(TypeError):
            GraphRAGAdapter()

    def test_subclass_must_implement_build(self):
        from src.app.services.graphrag.adapter import GraphRAGAdapter

        class BadAdapter(GraphRAGAdapter):
            pass

        with pytest.raises(TypeError):
            BadAdapter()


class TestBuiltinAdapter:
    def test_instantiates(self):
        from src.app.services.graphrag.adapter import BuiltinAdapter
        adapter = BuiltinAdapter()
        assert adapter is not None

    @pytest.mark.asyncio
    async def test_build_delegates_to_pipeline(self):
        from src.app.services.graphrag.adapter import BuiltinAdapter
        from src.app.services.graphrag.pipeline import KnowledgeGraph

        adapter = BuiltinAdapter()
        mock_kg = KnowledgeGraph(
            entities=[{"name": "test", "type": "org"}],
            relations=[],
            communities=[],
        )

        with patch.object(adapter, "_pipeline") as mock_pipe:
            mock_pipe.run = AsyncMock(return_value=mock_kg)
            session = MagicMock()
            result = await adapter.build_knowledge_graph(
                session=session,
                run_id="run-1",
                document_text="test doc",
                theme="test theme",
            )

        assert result is mock_kg
        mock_pipe.run.assert_called_once()
        call_args = mock_pipe.run.call_args
        assert call_args[0][1] == "run-1"
        assert call_args[0][2] == "test doc"
        assert call_args[1]["theme"] == "test theme"

    def test_has_name(self):
        from src.app.services.graphrag.adapter import BuiltinAdapter
        assert BuiltinAdapter().name == "builtin"


class TestAdapterFactory:
    def test_create_default_returns_builtin(self):
        from src.app.services.graphrag.adapter import create_adapter

        adapter = create_adapter()
        assert adapter.name == "builtin"

    def test_create_builtin_explicit(self):
        from src.app.services.graphrag.adapter import create_adapter

        adapter = create_adapter("builtin")
        assert adapter.name == "builtin"

    def test_create_unknown_raises(self):
        from src.app.services.graphrag.adapter import create_adapter

        with pytest.raises(ValueError, match="Unknown"):
            create_adapter("nonexistent")

    def test_create_from_config(self):
        from src.app.services.graphrag.adapter import create_adapter

        with patch("src.app.services.graphrag.adapter.settings") as mock_settings:
            mock_settings.load_graphrag_config.return_value = {"adapter": "builtin"}
            adapter = create_adapter()
            assert adapter.name == "builtin"

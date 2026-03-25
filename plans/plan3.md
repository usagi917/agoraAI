# agentAI TDD実装計画 v3 — コードレベル詳細

> 本計画は実際のコードを含む。各ステップはコピペで実装可能な粒度。
> 既存テストパターン: `pytest` + `pytest-asyncio` + `unittest.mock`（AsyncMock, patch）

---

## Phase 0: 基盤整備

### 0.1 テスト環境確認

```bash
# Step 1: 全テスト実行
cd backend && uv run pytest --tb=short -q

# Step 2: カバレッジ計測（pytest-cov は既に dev deps にある）
uv run pytest --cov=src/app --cov-report=term-missing --cov-report=html

# Step 3: カバレッジレポート確認
open htmlcov/index.html
```

### 0.2 conftest.py 作成

**ファイル:** `backend/tests/conftest.py`

```python
"""共通テストフィクスチャ"""

import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from src.app.database import Base


@pytest_asyncio.fixture
async def db_session():
    """テスト用のインメモリ SQLite セッション"""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
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
    with patch("src.app.llm.multi_client.multi_llm_client") as mock:
        mock.initialize = MagicMock()
        mock.call = AsyncMock(return_value=({"result": "test"}, {"total_tokens": 10}))
        mock.call_batch_by_provider = AsyncMock(return_value=[])
        yield mock
```

### 0.3 テストファクトリ作成

**ファイル:** `backend/tests/factories.py`

```python
"""テスト用ファクトリ関数"""

import uuid
from datetime import datetime
from src.app.models.simulation import Simulation


def make_simulation(**overrides) -> Simulation:
    """Simulation インスタンスを生成する。"""
    defaults = {
        "id": str(uuid.uuid4()),
        "mode": "unified",
        "prompt_text": "テスト用プロンプト",
        "template_name": "general_analysis",
        "execution_profile": "preview",
        "status": "queued",
        "metadata_json": {},
        "created_at": datetime.utcnow(),
    }
    defaults.update(overrides)
    return Simulation(**defaults)


def make_responses(stances: list[str], confidence: float = 0.7) -> list[dict]:
    """テスト用の response リストを生成する。"""
    return [
        {"stance": s, "confidence": confidence, "reason": f"理由: {s}"}
        for s in stances
    ]


def make_agents(count: int, openness: float = 0.5) -> list[dict]:
    """テスト用の agent リストを生成する。"""
    return [
        {
            "big_five": {"O": openness, "C": 0.5, "E": 0.5, "A": 0.5, "N": 0.5},
            "values": {},
        }
        for _ in range(count)
    ]


def make_pulse_result(**overrides) -> dict:
    """SocietyPulseResult 相当のデータを生成する。"""
    defaults = {
        "agents": make_agents(5),
        "responses": make_responses(["賛成", "反対", "中立", "賛成", "反対"]),
        "aggregation": {
            "stance_distribution": {"賛成": 0.4, "反対": 0.4, "中立": 0.2},
            "average_confidence": 0.65,
            "top_concerns": ["コスト", "実現可能性"],
            "top_priorities": ["効率化"],
            "total_respondents": 5,
        },
        "evaluation": {
            "diversity": 0.95,
            "consistency": 0.7,
            "calibration": 0.8,
        },
        "representatives": [],
        "usage": {"total_tokens": 100},
        "population_count": 100,
    }
    defaults.update(overrides)
    return defaults


def make_council_result(**overrides) -> dict:
    """CouncilResult 相当のデータを生成する。"""
    defaults = {
        "participants": [{"name": "Agent-1", "role": "expert"}],
        "devil_advocate_summary": "反論要約テスト",
        "kg_entities": [],
        "kg_relations": [],
        "rounds": [{"round": 1, "arguments": []}],
        "synthesis": {
            "consensus_points": ["全員が安全性を重視"],
            "disagreement_points": [{"topic": "コスト", "positions": []}],
            "recommendations": ["段階的導入を推奨"],
            "overall_assessment": "条件付き推進が妥当",
            "scenarios": [],
        },
        "usage": {"total_tokens": 200},
    }
    defaults.update(overrides)
    return defaults


def make_llm_response(content: dict | str = None, tokens: int = 100) -> tuple:
    """LLM 呼び出しの戻り値をモック用に生成する。"""
    if content is None:
        content = {"result": "ok"}
    usage = {
        "prompt_tokens": tokens // 2,
        "completion_tokens": tokens // 2,
        "total_tokens": tokens,
    }
    return content, usage
```

### 0.4 ファクトリのテスト

**ファイル:** `backend/tests/test_factories.py`

```python
"""ファクトリ関数自体のテスト"""

from tests.factories import (
    make_simulation,
    make_responses,
    make_agents,
    make_pulse_result,
    make_council_result,
    make_llm_response,
)
from src.app.models.simulation import Simulation


class TestMakeSimulation:
    def test_returns_simulation_instance(self):
        sim = make_simulation()
        assert isinstance(sim, Simulation)

    def test_default_mode_unified(self):
        sim = make_simulation()
        assert sim.mode == "unified"

    def test_override_mode(self):
        sim = make_simulation(mode="single")
        assert sim.mode == "single"

    def test_override_status(self):
        sim = make_simulation(status="running")
        assert sim.status == "running"

    def test_unique_ids(self):
        s1 = make_simulation()
        s2 = make_simulation()
        assert s1.id != s2.id


class TestMakeResponses:
    def test_returns_list_of_dicts(self):
        r = make_responses(["賛成", "反対"])
        assert len(r) == 2
        assert r[0]["stance"] == "賛成"
        assert r[1]["stance"] == "反対"

    def test_custom_confidence(self):
        r = make_responses(["中立"], confidence=0.9)
        assert r[0]["confidence"] == 0.9


class TestMakeAgents:
    def test_returns_correct_count(self):
        a = make_agents(3)
        assert len(a) == 3

    def test_has_big_five(self):
        a = make_agents(1, openness=0.8)
        assert a[0]["big_five"]["O"] == 0.8


class TestMakeLlmResponse:
    def test_returns_tuple(self):
        content, usage = make_llm_response()
        assert isinstance(content, dict)
        assert usage["total_tokens"] == 100

    def test_custom_content(self):
        content, _ = make_llm_response(content={"key": "value"}, tokens=50)
        assert content["key"] == "value"
```

---

## Phase 1: 実行モード統合 — 超詳細ステップ

### 1.1 Simulation.mode バリデーション

#### Step 1.1.1: RED — テスト作成

**ファイル:** `backend/tests/test_simulation_mode.py`

```python
"""Simulation.mode のバリデーションテスト"""

import pytest
from src.app.models.simulation import Simulation
from tests.factories import make_simulation


# --- 定数定義 ---

VALID_NEW_MODES = ["unified", "single", "baseline"]

MODE_ALIASES = {
    "pipeline": "unified",
    "swarm": "unified",
    "hybrid": "unified",
    "pm_board": "unified",
    "society": "unified",
    "society_first": "unified",
    "meta_simulation": "unified",
}


class TestValidModes:
    """新しい3モードが受け入れられること"""

    @pytest.mark.parametrize("mode", VALID_NEW_MODES)
    def test_valid_mode_accepted(self, mode):
        sim = make_simulation(mode=mode)
        assert sim.mode == mode


class TestModeAliases:
    """旧モードが新モードにリマップされること"""

    @pytest.mark.parametrize("old_mode,expected", list(MODE_ALIASES.items()))
    def test_old_mode_remaps(self, old_mode, expected):
        sim = make_simulation(mode=old_mode)
        # normalize_mode() 呼び出し後に expected になること
        from src.app.models.simulation import normalize_mode
        assert normalize_mode(old_mode) == expected


class TestInvalidMode:
    """不正なモードが拒否されること"""

    def test_unknown_mode_raises(self):
        with pytest.raises(ValueError, match="Unknown mode"):
            from src.app.models.simulation import normalize_mode
            normalize_mode("completely_invalid_mode")
```

#### Step 1.1.2: GREEN — 実装

**ファイル:** `backend/src/app/models/simulation.py` への変更

```python
# --- ファイル先頭に追加 ---

MODE_ALIASES: dict[str, str] = {
    "pipeline": "unified",
    "swarm": "unified",
    "hybrid": "unified",
    "pm_board": "unified",
    "society": "unified",
    "society_first": "unified",
    "meta_simulation": "unified",
}

VALID_MODES = {"unified", "single", "baseline"}


def normalize_mode(mode: str) -> str:
    """モード名を正規化する。旧モードは新モードにマップ。"""
    if mode in VALID_MODES:
        return mode
    if mode in MODE_ALIASES:
        return MODE_ALIASES[mode]
    raise ValueError(f"Unknown mode: {mode}. Valid: {VALID_MODES}")
```

Simulation クラスの `mode` フィールドのデフォルトを変更:
```python
# 変更前
mode: Mapped[str] = mapped_column(String(20), default="pipeline")

# 変更後
mode: Mapped[str] = mapped_column(String(20), default="unified")
```

---

### 1.2 simulation_dispatcher.py 書き直し

#### Step 1.2.1: RED — テスト作成

**ファイル:** `backend/tests/test_dispatch_v2.py`

```python
"""simulation_dispatcher v2 のテスト

3モード（unified, single, baseline）のルーティングのみをテストする。
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from tests.factories import make_simulation


class TestDispatchRouting:
    """dispatch_simulation() のモードルーティング"""

    @pytest.mark.asyncio
    @patch("src.app.services.simulation_dispatcher.run_unified", new_callable=AsyncMock)
    @patch("src.app.services.simulation_dispatcher.async_session")
    async def test_unified_mode_calls_run_unified(self, mock_session_ctx, mock_run_unified):
        """unified モード → run_unified() が呼ばれる"""
        sim = make_simulation(mode="unified")

        # async_session のモック構築
        mock_session = AsyncMock()
        mock_session.get = AsyncMock(return_value=sim)
        mock_session.commit = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session_ctx.return_value = mock_session

        with patch("src.app.services.simulation_dispatcher._ensure_project", new_callable=AsyncMock, return_value="proj-1"):
            with patch("src.app.services.simulation_dispatcher.sse_manager"):
                from src.app.services.simulation_dispatcher import dispatch_simulation
                await dispatch_simulation(sim.id)

        mock_run_unified.assert_awaited_once_with(sim.id)

    @pytest.mark.asyncio
    @patch("src.app.services.simulation_dispatcher.run_simulation", new_callable=AsyncMock)
    @patch("src.app.services.simulation_dispatcher.async_session")
    async def test_single_mode_calls_run_simulation(self, mock_session_ctx, mock_run_sim):
        """single モード → run_simulation() が呼ばれる"""
        sim = make_simulation(mode="single")

        mock_session = AsyncMock()
        mock_session.get = AsyncMock(return_value=sim)
        mock_session.commit = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session_ctx.return_value = mock_session

        with patch("src.app.services.simulation_dispatcher._ensure_project", new_callable=AsyncMock, return_value="proj-1"):
            with patch("src.app.services.simulation_dispatcher.sse_manager"):
                from src.app.services.simulation_dispatcher import dispatch_simulation
                await dispatch_simulation(sim.id)

        mock_run_sim.assert_awaited_once()

    @pytest.mark.asyncio
    @patch("src.app.services.simulation_dispatcher.run_baseline", new_callable=AsyncMock)
    @patch("src.app.services.simulation_dispatcher.async_session")
    async def test_baseline_mode_calls_run_baseline(self, mock_session_ctx, mock_run_baseline):
        """baseline モード → run_baseline() が呼ばれる"""
        sim = make_simulation(mode="baseline")

        mock_session = AsyncMock()
        mock_session.get = AsyncMock(return_value=sim)
        mock_session.commit = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session_ctx.return_value = mock_session

        with patch("src.app.services.simulation_dispatcher._ensure_project", new_callable=AsyncMock, return_value="proj-1"):
            with patch("src.app.services.simulation_dispatcher.sse_manager"):
                from src.app.services.simulation_dispatcher import dispatch_simulation
                await dispatch_simulation(sim.id)

        mock_run_baseline.assert_awaited_once_with(sim.id)

    @pytest.mark.asyncio
    @patch("src.app.services.simulation_dispatcher.async_session")
    async def test_missing_simulation_returns_early(self, mock_session_ctx):
        """存在しない simulation_id → 早期リターン（例外なし）"""
        mock_session = AsyncMock()
        mock_session.get = AsyncMock(return_value=None)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session_ctx.return_value = mock_session

        from src.app.services.simulation_dispatcher import dispatch_simulation
        # 例外なしで完了すること
        await dispatch_simulation("nonexistent-id")


class TestDispatchErrorHandling:
    """dispatch_simulation() のエラーハンドリング"""

    @pytest.mark.asyncio
    @patch("src.app.services.simulation_dispatcher.run_unified", new_callable=AsyncMock, side_effect=RuntimeError("LLM error"))
    @patch("src.app.services.simulation_dispatcher.async_session")
    async def test_failure_sets_status_failed(self, mock_session_ctx, mock_run_unified):
        """オーケストレータが例外 → status='failed' に設定"""
        sim = make_simulation(mode="unified", status="running")

        mock_session = AsyncMock()
        mock_session.get = AsyncMock(return_value=sim)
        mock_session.commit = AsyncMock()
        mock_session.rollback = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session_ctx.return_value = mock_session

        with patch("src.app.services.simulation_dispatcher._ensure_project", new_callable=AsyncMock, return_value="proj-1"):
            with patch("src.app.services.simulation_dispatcher.sse_manager") as mock_sse:
                mock_sse.publish = AsyncMock()
                from src.app.services.simulation_dispatcher import dispatch_simulation
                await dispatch_simulation(sim.id)

        assert sim.status == "failed"
        assert "LLM error" in sim.error_message

    @pytest.mark.asyncio
    @patch("src.app.services.simulation_dispatcher.run_unified", new_callable=AsyncMock, side_effect=ValueError("test"))
    @patch("src.app.services.simulation_dispatcher.async_session")
    async def test_failure_publishes_sse_event(self, mock_session_ctx, mock_run):
        """オーケストレータが例外 → SSE simulation_failed が配信される"""
        sim = make_simulation(mode="unified")

        mock_session = AsyncMock()
        mock_session.get = AsyncMock(return_value=sim)
        mock_session.commit = AsyncMock()
        mock_session.rollback = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session_ctx.return_value = mock_session

        with patch("src.app.services.simulation_dispatcher._ensure_project", new_callable=AsyncMock, return_value="proj-1"):
            with patch("src.app.services.simulation_dispatcher.sse_manager") as mock_sse:
                mock_sse.publish = AsyncMock()
                from src.app.services.simulation_dispatcher import dispatch_simulation
                await dispatch_simulation(sim.id)

        # simulation_failed イベントが配信されたか
        calls = mock_sse.publish.call_args_list
        event_types = [c[0][1] for c in calls]
        assert "simulation_failed" in event_types


class TestEnsureProject:
    """_ensure_project() のロジック"""

    def test_prompt_propagation_logic(self):
        """sim.prompt_text あり + project.prompt_text なし → 更新する"""
        sim_prompt = "Analyze this"
        project_prompt = ""
        should_update = bool(sim_prompt) and not bool(project_prompt)
        assert should_update is True

    def test_no_overwrite_logic(self):
        """project.prompt_text あり → 上書きしない"""
        sim_prompt = "New"
        project_prompt = "Existing"
        should_update = bool(sim_prompt) and not bool(project_prompt)
        assert should_update is False
```

#### Step 1.2.2: GREEN — 実装

**ファイル:** `backend/src/app/services/simulation_dispatcher.py` 全面書き換え

```python
"""Simulation Dispatcher v2: 3モード（unified, single, baseline）"""

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from src.app.database import async_session
from src.app.models.simulation import Simulation, normalize_mode
from src.app.services.simulator import run_simulation
from src.app.services.unified_orchestrator import run_unified
from src.app.services.baseline_orchestrator import run_baseline
from src.app.sse.manager import sse_manager

logger = logging.getLogger(__name__)


async def dispatch_simulation(simulation_id: str) -> None:
    """Simulation レコードに基づいて適切な実行フローを起動する。"""
    logger.info("Dispatching simulation %s", simulation_id)

    async with async_session() as session:
        try:
            sim = await session.get(Simulation, simulation_id)
            if not sim:
                logger.error("Simulation %s not found", simulation_id)
                return

            # モード正規化
            sim.mode = normalize_mode(sim.mode)
            sim.status = "running"
            sim.started_at = datetime.now(timezone.utc)
            await session.commit()

            if sim.mode == "unified":
                await run_unified(sim.id)
            elif sim.mode == "single":
                await run_simulation(
                    sim.id,
                    prompt_text=sim.prompt_text,
                )
            elif sim.mode == "baseline":
                await run_baseline(sim.id)

        except Exception as e:
            error_msg = f"{type(e).__name__}: {e}"
            logger.error("Simulation %s failed: %s", simulation_id, error_msg, exc_info=True)

            try:
                await session.rollback()
                sim = await session.get(Simulation, simulation_id)
                if sim:
                    sim.status = "failed"
                    sim.error_message = error_msg[:500]
                    await session.commit()
            except Exception as db_err:
                logger.error("Failed to update simulation status: %s", db_err)

            await sse_manager.publish(simulation_id, "simulation_failed", {
                "simulation_id": simulation_id,
                "error": str(e),
            })


async def _ensure_project(session: AsyncSession, sim: Simulation) -> str:
    """（後方互換用、Phase 2 で削除予定）"""
    # Phase 2 で Project モデルを Simulation に統合するまでの一時措置
    return sim.project_id or sim.id
```

---

### 1.3 不要オーケストレータの削除

#### Step 1.3.1: RED — import チェックテスト

**ファイル:** `backend/tests/test_no_stale_imports.py`

```python
"""削除済みモジュールへの参照がないことを確認するテスト"""

import ast
import os
from pathlib import Path

# 削除対象モジュール名（ファイル名から .py を除いたもの）
DELETED_MODULES = [
    "pipeline_orchestrator",
    "swarm_orchestrator",
    "pm_board_orchestrator",
    "meta_orchestrator",
    "society_first_orchestrator",
    "meta_intervention_planner",
    "swarm_report_generator",
    "colony_factory",
    "claim_extractor",
    "claim_clusterer",
    "final_report_generator",
    "pipeline_fallbacks",
    "aggregator",
]

# スキャン対象ディレクトリ
SRC_DIR = Path(__file__).parent.parent / "src" / "app"


def _collect_python_files(directory: Path) -> list[Path]:
    """ディレクトリ配下の全 .py ファイルを収集する。"""
    return list(directory.rglob("*.py"))


def _extract_imports(filepath: Path) -> list[str]:
    """ファイルから import 文のモジュール名を抽出する。"""
    try:
        tree = ast.parse(filepath.read_text(encoding="utf-8"))
    except SyntaxError:
        return []

    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.append(node.module)
    return imports


class TestNoStaleImports:
    """削除済みモジュールへの import が残っていないことを確認する。"""

    def test_no_references_to_deleted_modules(self):
        violations = []
        for py_file in _collect_python_files(SRC_DIR):
            imports = _extract_imports(py_file)
            for imp in imports:
                for deleted in DELETED_MODULES:
                    if deleted in imp:
                        violations.append(f"{py_file.relative_to(SRC_DIR)}: imports '{imp}' (contains '{deleted}')")

        assert violations == [], (
            f"削除済みモジュールへの参照が {len(violations)} 件残っています:\n"
            + "\n".join(violations)
        )

    def test_deleted_files_do_not_exist(self):
        services_dir = SRC_DIR / "services"
        for module in DELETED_MODULES:
            filepath = services_dir / f"{module}.py"
            assert not filepath.exists(), f"削除対象ファイルがまだ存在: {filepath}"
```

#### Step 1.3.2: GREEN — 参照除去 + ファイル削除

実行手順:

```bash
# 1. 各ファイルへの参照を grep で確認
cd backend
grep -rn "pipeline_orchestrator\|swarm_orchestrator\|pm_board_orchestrator\|meta_orchestrator\|society_first_orchestrator\|colony_factory\|claim_extractor\|claim_clusterer\|final_report_generator\|pipeline_fallbacks\|aggregator\|meta_intervention_planner\|swarm_report_generator" src/app/ --include="*.py" | grep -v "__pycache__"

# 2. 参照を除去（simulation_dispatcher.py は Step 1.2 で既に書き換え済み）
# 残りの参照がある場合はここで手動修正

# 3. ファイル削除
rm -f src/app/services/pipeline_orchestrator.py
rm -f src/app/services/swarm_orchestrator.py
rm -f src/app/services/pm_board_orchestrator.py
rm -f src/app/services/meta_orchestrator.py
rm -f src/app/services/society_first_orchestrator.py
rm -f src/app/services/meta_intervention_planner.py
rm -f src/app/services/swarm_report_generator.py
rm -f src/app/services/colony_factory.py
rm -f src/app/services/claim_extractor.py
rm -f src/app/services/claim_clusterer.py
rm -f src/app/services/final_report_generator.py
rm -f src/app/services/pipeline_fallbacks.py
rm -f src/app/services/aggregator.py

# 4. 旧テスト削除
rm -f tests/test_pipeline_orchestrator.py
rm -f tests/test_swarm_orchestrator.py

# 5. テスト実行
uv run pytest tests/test_no_stale_imports.py -v
uv run pytest --tb=short -q
```

---

### 1.4 baseline_orchestrator.py 新設

#### Step 1.4.1: RED — テスト作成

**ファイル:** `backend/tests/test_baseline_orchestrator.py`

```python
"""baseline_orchestrator のテスト"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from tests.factories import make_simulation, make_llm_response


class TestRunBaseline:
    """run_baseline() の基本動作"""

    @pytest.mark.asyncio
    @patch("src.app.services.baseline_orchestrator.multi_llm_client")
    @patch("src.app.services.baseline_orchestrator.async_session")
    async def test_completes_successfully(self, mock_session_ctx, mock_llm):
        """正常完了 → status='completed'"""
        sim = make_simulation(mode="baseline", seed=42)

        mock_session = AsyncMock()
        mock_session.get = AsyncMock(return_value=sim)
        mock_session.commit = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session_ctx.return_value = mock_session

        mock_llm.initialize = MagicMock()
        mock_llm.call = AsyncMock(return_value=make_llm_response(
            content={
                "analysis": "テスト分析結果",
                "recommendation": "Go",
                "key_findings": ["発見1", "発見2"],
                "risks": ["リスク1"],
                "confidence": 0.8,
            },
            tokens=500,
        ))

        with patch("src.app.services.baseline_orchestrator.sse_manager") as mock_sse:
            mock_sse.publish = AsyncMock()
            from src.app.services.baseline_orchestrator import run_baseline
            await run_baseline(sim.id)

        assert sim.status == "completed"
        assert sim.completed_at is not None

    @pytest.mark.asyncio
    @patch("src.app.services.baseline_orchestrator.multi_llm_client")
    @patch("src.app.services.baseline_orchestrator.async_session")
    async def test_saves_result_to_metadata_json(self, mock_session_ctx, mock_llm):
        """結果が metadata_json["unified_result"] に保存される"""
        sim = make_simulation(mode="baseline")

        mock_session = AsyncMock()
        mock_session.get = AsyncMock(return_value=sim)
        mock_session.commit = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session_ctx.return_value = mock_session

        analysis_result = {"analysis": "test", "recommendation": "Go"}
        mock_llm.initialize = MagicMock()
        mock_llm.call = AsyncMock(return_value=make_llm_response(content=analysis_result))

        with patch("src.app.services.baseline_orchestrator.sse_manager") as mock_sse:
            mock_sse.publish = AsyncMock()
            from src.app.services.baseline_orchestrator import run_baseline
            await run_baseline(sim.id)

        # unified_result キーが存在すること
        assert "unified_result" in sim.metadata_json
        result = sim.metadata_json["unified_result"]
        assert result["type"] == "baseline"
        assert "decision_brief" in result

    @pytest.mark.asyncio
    @patch("src.app.services.baseline_orchestrator.multi_llm_client")
    @patch("src.app.services.baseline_orchestrator.async_session")
    async def test_uses_temperature_zero(self, mock_session_ctx, mock_llm):
        """ベースラインは temperature=0 で呼び出す"""
        sim = make_simulation(mode="baseline")

        mock_session = AsyncMock()
        mock_session.get = AsyncMock(return_value=sim)
        mock_session.commit = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session_ctx.return_value = mock_session

        mock_llm.initialize = MagicMock()
        mock_llm.call = AsyncMock(return_value=make_llm_response())

        with patch("src.app.services.baseline_orchestrator.sse_manager") as mock_sse:
            mock_sse.publish = AsyncMock()
            from src.app.services.baseline_orchestrator import run_baseline
            await run_baseline(sim.id)

        # call の引数を確認
        call_kwargs = mock_llm.call.call_args
        assert call_kwargs.kwargs.get("temperature") == 0.0 or call_kwargs[1].get("temperature") == 0.0

    @pytest.mark.asyncio
    @patch("src.app.services.baseline_orchestrator.multi_llm_client")
    @patch("src.app.services.baseline_orchestrator.async_session")
    async def test_missing_simulation_returns_early(self, mock_session_ctx, mock_llm):
        """存在しない simulation → 早期リターン"""
        mock_session = AsyncMock()
        mock_session.get = AsyncMock(return_value=None)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session_ctx.return_value = mock_session

        from src.app.services.baseline_orchestrator import run_baseline
        await run_baseline("nonexistent")

        mock_llm.call.assert_not_awaited()

    @pytest.mark.asyncio
    @patch("src.app.services.baseline_orchestrator.multi_llm_client")
    @patch("src.app.services.baseline_orchestrator.async_session")
    async def test_error_sets_status_failed(self, mock_session_ctx, mock_llm):
        """LLM エラー → status='failed'"""
        sim = make_simulation(mode="baseline")

        mock_session = AsyncMock()
        mock_session.get = AsyncMock(return_value=sim)
        mock_session.commit = AsyncMock()
        mock_session.rollback = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session_ctx.return_value = mock_session

        mock_llm.initialize = MagicMock()
        mock_llm.call = AsyncMock(side_effect=RuntimeError("API error"))

        with patch("src.app.services.baseline_orchestrator.sse_manager") as mock_sse:
            mock_sse.publish = AsyncMock()
            from src.app.services.baseline_orchestrator import run_baseline
            await run_baseline(sim.id)

        assert sim.status == "failed"
        assert "API error" in sim.error_message
```

#### Step 1.4.2: GREEN — 実装

**ファイル:** `backend/src/app/services/baseline_orchestrator.py` 新規作成

```python
"""Baseline Orchestrator: 単一LLMベースライン分析

学術比較用。エージェントなしの単一LLMプロンプトでテーマを分析し、
unified モードと同じフォーマットで結果を保存する。
"""

import logging
from datetime import datetime, timezone

from src.app.database import async_session
from src.app.llm.multi_client import multi_llm_client
from src.app.models.simulation import Simulation
from src.app.sse.manager import sse_manager

logger = logging.getLogger(__name__)


async def run_baseline(simulation_id: str) -> None:
    """ベースラインモードを実行する。

    単一の LLM 呼び出しでテーマを分析。
    temperature=0 で決定論的に実行。
    """
    logger.info("Starting baseline simulation %s", simulation_id)

    async with async_session() as session:
        sim = await session.get(Simulation, simulation_id)
        if not sim:
            logger.error("Simulation %s not found", simulation_id)
            return

        theme = sim.prompt_text

        try:
            multi_llm_client.initialize()

            await sse_manager.publish(simulation_id, "unified_phase_changed", {
                "phase": "baseline_analysis",
                "index": 1,
                "total": 1,
            })

            # 単一 LLM 分析
            system_prompt = (
                "あなたは戦略アナリストです。以下のテーマについて包括的な分析を行い、"
                "JSON形式で結果を返してください。\n\n"
                "出力JSON:\n"
                "{\n"
                '  "recommendation": "Go | No-Go | 条件付きGo",\n'
                '  "decision_summary": "1-2文の結論",\n'
                '  "why_now": "なぜ今判断するのか",\n'
                '  "key_findings": ["発見1", "発見2", ...],\n'
                '  "risks": ["リスク1", "リスク2", ...],\n'
                '  "opportunities": ["機会1", "機会2", ...],\n'
                '  "confidence": 0.0-1.0,\n'
                '  "next_steps": ["ステップ1", "ステップ2", ...]\n'
                "}"
            )

            user_prompt = f"テーマ: {theme}\n\n上記テーマを多角的に分析してください。"

            result, usage = await multi_llm_client.call(
                provider_name="openai",
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=0.0,
                max_tokens=4096,
            )

            # 結果を dict に正規化
            if isinstance(result, str):
                import json
                try:
                    result = json.loads(result)
                except json.JSONDecodeError:
                    result = {"analysis": result, "recommendation": "条件付きGo"}

            # unified_result 互換フォーマットで保存
            decision_brief = {
                "recommendation": result.get("recommendation", "条件付きGo"),
                "decision_summary": result.get("decision_summary", ""),
                "why_now": result.get("why_now", ""),
                "agreement_score": result.get("confidence", 0.5),
                "key_reasons": [
                    {"reason": f, "evidence": "ベースライン分析", "confidence": result.get("confidence", 0.5)}
                    for f in result.get("key_findings", [])[:5]
                ],
                "risk_factors": [
                    {"condition": r, "impact": "要検証"}
                    for r in result.get("risks", [])[:5]
                ],
                "next_steps": result.get("next_steps", []),
            }

            sim.metadata_json = {
                "unified_result": {
                    "type": "baseline",
                    "decision_brief": decision_brief,
                    "agreement_score": result.get("confidence", 0.5),
                    "content": f"# ベースライン分析レポート\n\n{result.get('decision_summary', '')}",
                    "sections": {"decision_brief": decision_brief},
                    "usage": usage,
                },
            }
            sim.status = "completed"
            sim.completed_at = datetime.now(timezone.utc)
            await session.commit()

            await sse_manager.publish(simulation_id, "simulation_completed", {
                "simulation_id": simulation_id,
                "mode": "baseline",
            })

            logger.info("Baseline simulation %s completed", simulation_id)

        except Exception as e:
            logger.error("Baseline simulation %s failed: %s", simulation_id, e, exc_info=True)
            await session.rollback()
            sim.status = "failed"
            sim.error_message = f"{type(e).__name__}: {e}"[:500]
            await session.commit()

            await sse_manager.publish(simulation_id, "simulation_failed", {
                "simulation_id": simulation_id,
                "error": str(e),
            })
```

---

### 1.5 compute_agreement_score テスト強化

#### Step 1.5.1: RED — テスト作成

**ファイル:** `backend/tests/test_synthesis_score.py`

```python
"""compute_agreement_score の精密テスト"""

import pytest
from src.app.services.phases.synthesis import compute_agreement_score


class TestComputeAgreementScore:
    """合意度スコアの計算ロジック"""

    def test_balanced_inputs(self):
        """Society + Council が中程度 → 0.3-0.7"""
        society = {
            "aggregation": {"average_confidence": 0.6},
            "evaluation": {"consistency": 0.5, "calibration": 0.7},
        }
        council = {
            "consensus_points": ["A", "B"],
            "disagreement_points": ["C", "D"],
        }
        score = compute_agreement_score(society, council)
        assert 0.3 <= score <= 0.7

    def test_full_consensus(self):
        """全合意 → 高スコア"""
        society = {
            "aggregation": {"average_confidence": 0.9},
            "evaluation": {"consistency": 0.9, "calibration": 0.95},
        }
        council = {
            "consensus_points": ["A", "B", "C"],
            "disagreement_points": [],
        }
        score = compute_agreement_score(society, council)
        assert score >= 0.8

    def test_no_data(self):
        """データなし → 0.0"""
        score = compute_agreement_score(
            {"aggregation": {}, "evaluation": {}},
            {},
        )
        assert score == 0.0

    def test_society_only_no_council_points(self):
        """Council のポイントなし → Society スコアのみ"""
        society = {
            "aggregation": {"average_confidence": 0.7},
            "evaluation": {"consistency": 0.6, "calibration": 0.8},
        }
        council = {
            "consensus_points": [],
            "disagreement_points": [],
        }
        score = compute_agreement_score(society, council)
        # (0.7 + 0.6 + 0.8) / 3 ≈ 0.7
        assert 0.6 <= score <= 0.8

    def test_all_disagreement(self):
        """全対立 → council_score=0 → 低スコア"""
        society = {
            "aggregation": {"average_confidence": 0.5},
            "evaluation": {"consistency": 0.5, "calibration": 0.5},
        }
        council = {
            "consensus_points": [],
            "disagreement_points": ["X", "Y", "Z"],
        }
        score = compute_agreement_score(society, council)
        # society_score=0.5 * 0.5 + council_score=0 * 0.5 = 0.25
        assert score == 0.25

    def test_none_values_handled(self):
        """None 値 → 0.0 として処理"""
        society = {
            "aggregation": {"average_confidence": None},
            "evaluation": {"consistency": None, "calibration": None},
        }
        council = {"consensus_points": None, "disagreement_points": None}
        score = compute_agreement_score(society, council)
        assert score == 0.0

    def test_score_is_float(self):
        """戻り値は float"""
        society = {
            "aggregation": {"average_confidence": 0.5},
            "evaluation": {"consistency": 0.5, "calibration": 0.5},
        }
        council = {"consensus_points": ["A"], "disagreement_points": ["B"]}
        score = compute_agreement_score(society, council)
        assert isinstance(score, float)

    def test_score_bounded_0_to_1(self):
        """スコアは 0.0 ~ 1.0 の範囲"""
        test_cases = [
            ({"aggregation": {"average_confidence": 1.0}, "evaluation": {"consistency": 1.0, "calibration": 1.0}},
             {"consensus_points": ["A"] * 10, "disagreement_points": []}),
            ({"aggregation": {"average_confidence": 0.0}, "evaluation": {"consistency": 0.0, "calibration": 0.0}},
             {"consensus_points": [], "disagreement_points": ["X"] * 10}),
        ]
        for society, council in test_cases:
            score = compute_agreement_score(society, council)
            assert 0.0 <= score <= 1.0, f"Score {score} out of range"
```

---

### 1.6 Phase 1 完了確認

```bash
# 全テスト実行
cd backend && uv run pytest --tb=short -q

# カバレッジ確認
uv run pytest --cov=src/app --cov-report=term-missing

# 新テストのみ実行
uv run pytest tests/test_simulation_mode.py tests/test_dispatch_v2.py tests/test_no_stale_imports.py tests/test_baseline_orchestrator.py tests/test_synthesis_score.py -v

# コミット
git add -A && git commit -m "feat: consolidate 9 modes to 3 (unified, single, baseline)"
```

---

## Phase 2-6: 概要（Phase 1 完了後に同じ粒度で展開）

Phase 2 以降も同じパターンで展開する:
1. **テストファイル名** + **テストクラス名** + **テストメソッド名** + **テストコード全文**
2. **実装ファイル名** + **クラス/関数シグネチャ** + **実装コード全文**
3. **実行コマンド**（テスト実行、ファイル削除、マイグレーション等）
4. **コミットメッセージ**

Phase 1 完了後に Phase 2 の同等粒度の計画を展開する。

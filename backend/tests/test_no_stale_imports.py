"""削除済みモジュールへの参照がないことを確認するテスト"""

import ast
from pathlib import Path

# 削除対象オーケストレータ（pm_board_orchestrator は pm_analysis.py が利用するため除外）
DELETED_ORCHESTRATORS = [
    "pipeline_orchestrator",
    "swarm_orchestrator",
    "meta_orchestrator",
    "society_first_orchestrator",
]

SRC_DIR = Path(__file__).parent.parent / "src" / "app"

# 正当に旧モジュールを利用しているファイル or Phase 5 で対処するファイル
ALLOWED_EXCEPTIONS = {
    "services/phases/pm_analysis.py": {"pm_board_orchestrator"},
    "api/routes/swarms.py": {"swarm_orchestrator"},  # Phase 5 でルートごと削除
}


def _collect_python_files(directory: Path) -> list[Path]:
    return [p for p in directory.rglob("*.py") if "__pycache__" not in str(p)]


def _extract_imports(filepath: Path) -> list[str]:
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
    def test_no_references_to_deleted_orchestrators(self):
        violations = []
        for py_file in _collect_python_files(SRC_DIR):
            relative = str(py_file.relative_to(SRC_DIR))
            allowed = ALLOWED_EXCEPTIONS.get(relative, set())
            imports = _extract_imports(py_file)
            for imp in imports:
                for deleted in DELETED_ORCHESTRATORS:
                    if deleted in imp and deleted not in allowed:
                        violations.append(
                            f"{relative}: imports '{imp}' (contains '{deleted}')"
                        )

        assert violations == [], (
            f"削除済みオーケストレータへの参照が {len(violations)} 件残っています:\n"
            + "\n".join(violations)
        )

    def test_deleted_orchestrator_files_do_not_exist(self):
        services_dir = SRC_DIR / "services"
        for module in DELETED_ORCHESTRATORS:
            filepath = services_dir / f"{module}.py"
            assert not filepath.exists(), f"削除対象ファイルがまだ存在: {filepath}"

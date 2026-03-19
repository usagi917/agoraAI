"""graph_projection モジュールのテスト"""

from src.app.services.graph_projection import project_graph


def test_project_graph_empty():
    result = project_graph({})
    assert result["nodes"] == []
    assert result["edges"] == []


def test_project_graph_basic():
    world_state = {
        "entities": [
            {"id": "e1", "label": "Company A", "entity_type": "company", "importance_score": 0.9},
            {"id": "e2", "label": "Company B", "entity_type": "company", "importance_score": 0.7},
        ],
        "relations": [
            {"id": "r1", "source": "e1", "target": "e2", "weight": 0.8, "label": "competes_with"},
        ],
    }
    result = project_graph(world_state)
    assert len(result["nodes"]) == 2
    assert len(result["edges"]) == 1
    assert result["nodes"][0]["id"] == "e1"
    assert result["nodes"][0]["importance_score"] == 0.9


def test_project_graph_respects_max_nodes():
    entities = [
        {"id": f"e{i}", "label": f"Entity {i}", "importance_score": i / 100}
        for i in range(30)
    ]
    world_state = {"entities": entities, "relations": []}
    result = project_graph(world_state)
    assert len(result["nodes"]) <= 20


def test_project_graph_filters_edges_to_selected_nodes():
    entities = [
        {"id": "e1", "label": "A", "importance_score": 0.9},
        {"id": "e2", "label": "B", "importance_score": 0.8},
    ]
    relations = [
        {"source": "e1", "target": "e2", "weight": 1.0},
        {"source": "e1", "target": "e_missing", "weight": 0.5},
    ]
    world_state = {"entities": entities, "relations": relations}
    result = project_graph(world_state)
    assert len(result["edges"]) == 1
    assert result["edges"][0]["source"] == "e1"
    assert result["edges"][0]["target"] == "e2"


def test_project_graph_sorts_by_importance():
    entities = [
        {"id": "low", "label": "Low", "importance_score": 0.1},
        {"id": "high", "label": "High", "importance_score": 0.9},
        {"id": "mid", "label": "Mid", "importance_score": 0.5},
    ]
    result = project_graph({"entities": entities, "relations": []})
    ids = [n["id"] for n in result["nodes"]]
    assert ids == ["high", "mid", "low"]

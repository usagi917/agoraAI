"""data_grounding.py のテスト

TDD: RED → GREEN → REFACTOR
"""

from __future__ import annotations

import yaml
import pytest

from src.app.services.society.data_grounding import (
    load_grounding_facts,
    distribute_facts_to_agents,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def grounding_dir(tmp_path):
    """テスト用のグラウンディングデータを tmp ディレクトリに書き出す."""
    data = {
        "facts": [
            {
                "fact": "2024年の実質賃金は前年比-2.5%",
                "source": "厚生労働省 毎月勤労統計調査 2024年",
                "date": "2024-12",
                "category": "economy",
                "relevance_keywords": ["賃金", "給与", "収入", "労働", "雇用"],
            },
            {
                "fact": "2024年の合計特殊出生率は1.20",
                "source": "厚生労働省 人口動態統計 2024年",
                "date": "2024-12",
                "category": "demographics",
                "relevance_keywords": ["出生", "少子化", "人口", "子育て"],
            },
            {
                "fact": "2024年の完全失業率は2.6%",
                "source": "総務省 労働力調査 2024年",
                "date": "2024-12",
                "category": "economy",
                "relevance_keywords": ["失業", "雇用", "仕事", "労働", "就職"],
            },
        ]
    }
    econ_file = tmp_path / "economy.yaml"
    econ_file.write_text(yaml.dump(data, allow_unicode=True))
    return tmp_path


@pytest.fixture
def grounding_dir_multi(tmp_path):
    """複数のカテゴリファイルを持つ tmp ディレクトリ."""
    economy_data = {
        "facts": [
            {
                "fact": "2024年の実質賃金は前年比-2.5%",
                "source": "厚生労働省 毎月勤労統計調査 2024年",
                "date": "2024-12",
                "category": "economy",
                "relevance_keywords": ["賃金", "給与", "収入", "労働", "雇用"],
            },
        ]
    }
    agriculture_data = {
        "facts": [
            {
                "fact": "2024年の農業就業人口は約116万人",
                "source": "農林水産省 農林業センサス 2024年",
                "date": "2024-12",
                "category": "agriculture",
                "relevance_keywords": ["農業", "農家", "農村", "農作物", "農業従事者"],
            },
            {
                "fact": "2024年の食料自給率はカロリーベースで38%",
                "source": "農林水産省 食料需給表 2024年",
                "date": "2024-12",
                "category": "agriculture",
                "relevance_keywords": ["食料", "農業", "自給率", "食品"],
            },
        ]
    }
    (tmp_path / "economy.yaml").write_text(yaml.dump(economy_data, allow_unicode=True))
    (tmp_path / "agriculture.yaml").write_text(yaml.dump(agriculture_data, allow_unicode=True))
    return tmp_path


@pytest.fixture
def sample_agents():
    """テスト用のエージェントリスト."""
    return [
        {
            "id": 0,
            "demographics": {
                "occupation": "会社員",
                "region": "東京",
                "income_bracket": "中間層",
                "age": 35,
                "gender": "男性",
            },
        },
        {
            "id": 1,
            "demographics": {
                "occupation": "農業従事者",
                "region": "北海道",
                "income_bracket": "低所得層",
                "age": 55,
                "gender": "男性",
            },
        },
        {
            "id": 2,
            "demographics": {
                "occupation": "教員",
                "region": "大阪",
                "income_bracket": "中間層",
                "age": 42,
                "gender": "女性",
            },
        },
    ]


@pytest.fixture
def sample_facts():
    """テスト用のファクトリスト."""
    return [
        {
            "fact": "2024年の実質賃金は前年比-2.5%",
            "source": "厚生労働省 毎月勤労統計調査 2024年",
            "date": "2024-12",
            "category": "economy",
            "relevance_keywords": ["賃金", "給与", "収入", "労働", "雇用"],
        },
        {
            "fact": "2024年の農業就業人口は約116万人",
            "source": "農林水産省 農林業センサス 2024年",
            "date": "2024-12",
            "category": "agriculture",
            "relevance_keywords": ["農業", "農家", "農村", "農作物", "農業従事者"],
        },
        {
            "fact": "2024年の食料自給率はカロリーベースで38%",
            "source": "農林水産省 食料需給表 2024年",
            "date": "2024-12",
            "category": "agriculture",
            "relevance_keywords": ["食料", "農業", "自給率", "食品"],
        },
        {
            "fact": "2024年の合計特殊出生率は1.20",
            "source": "厚生労働省 人口動態統計 2024年",
            "date": "2024-12",
            "category": "demographics",
            "relevance_keywords": ["出生", "少子化", "人口", "子育て"],
        },
        {
            "fact": "2024年の完全失業率は2.6%",
            "source": "総務省 労働力調査 2024年",
            "date": "2024-12",
            "category": "economy",
            "relevance_keywords": ["失業", "雇用", "仕事", "労働", "就職"],
        },
    ]


# ---------------------------------------------------------------------------
# test_load_facts_returns_list
# ---------------------------------------------------------------------------

def test_load_facts_returns_list(grounding_dir):
    """load_grounding_facts はリストを返す."""
    result = load_grounding_facts("賃金政策", grounding_dir=grounding_dir)
    assert isinstance(result, list)


# ---------------------------------------------------------------------------
# test_load_facts_matches_theme_keywords
# ---------------------------------------------------------------------------

def test_load_facts_matches_theme_keywords(grounding_dir):
    """"賃金" テーマ → relevance_keywords に "賃金" を含むファクトが返る."""
    result = load_grounding_facts("賃金", grounding_dir=grounding_dir)
    assert len(result) >= 1
    # 少なくとも1件は "賃金" キーワードを含む
    matched = [
        f for f in result
        if "賃金" in f.get("relevance_keywords", [])
    ]
    assert len(matched) >= 1


def test_load_facts_returns_highest_matching_first(grounding_dir):
    """マッチスコアが高いファクトが先頭に来る."""
    result = load_grounding_facts("賃金 給与", grounding_dir=grounding_dir)
    # "賃金" と "給与" を両方含むファクトが先頭
    assert len(result) >= 1
    first = result[0]
    keywords = first.get("relevance_keywords", [])
    assert "賃金" in keywords or "給与" in keywords


# ---------------------------------------------------------------------------
# test_load_facts_no_match_returns_empty
# ---------------------------------------------------------------------------

def test_load_facts_no_match_returns_empty(grounding_dir):
    """テーマ "宇宙開発" → どのファクトにもマッチしないので空リスト."""
    result = load_grounding_facts("宇宙開発", grounding_dir=grounding_dir)
    assert result == []


def test_load_facts_empty_theme_returns_empty(grounding_dir):
    """空のテーマ文字列 → 空リスト."""
    result = load_grounding_facts("", grounding_dir=grounding_dir)
    assert result == []


def test_load_facts_from_multiple_yaml_files(grounding_dir_multi):
    """複数の YAML ファイルから facts を読み込む."""
    result = load_grounding_facts("農業", grounding_dir=grounding_dir_multi)
    assert len(result) >= 1
    matched = [f for f in result if "農業" in f.get("relevance_keywords", [])]
    assert len(matched) >= 1


def test_load_facts_max_10_results(tmp_path):
    """結果は最大10件に制限される."""
    # 15件のファクトを作成し、全て同じキーワードでマッチする
    facts = [
        {
            "fact": f"ファクト{i}",
            "source": f"出典{i}",
            "date": "2024-12",
            "category": "test",
            "relevance_keywords": ["テスト", "データ"],
        }
        for i in range(15)
    ]
    (tmp_path / "test.yaml").write_text(yaml.dump({"facts": facts}, allow_unicode=True))
    result = load_grounding_facts("テスト", grounding_dir=tmp_path)
    assert len(result) <= 10


# ---------------------------------------------------------------------------
# test_distribute_facts_respects_max_per_agent
# ---------------------------------------------------------------------------

def test_distribute_facts_respects_max_per_agent(sample_agents, sample_facts):
    """max_per_agent=2 → 各エージェントに最大2件."""
    result = distribute_facts_to_agents(sample_agents, sample_facts, max_per_agent=2)
    for idx in range(len(sample_agents)):
        assert len(result[idx]) <= 2


def test_distribute_facts_default_max(sample_agents, sample_facts):
    """max_per_agent のデフォルト=5 → 最大5件."""
    result = distribute_facts_to_agents(sample_agents, sample_facts)
    for idx in range(len(sample_agents)):
        assert len(result[idx]) <= 5


def test_distribute_facts_returns_dict_keyed_by_index(sample_agents, sample_facts):
    """返り値はエージェントインデックスをキーとする dict."""
    result = distribute_facts_to_agents(sample_agents, sample_facts, max_per_agent=3)
    assert isinstance(result, dict)
    for idx in range(len(sample_agents)):
        assert idx in result
        assert isinstance(result[idx], list)


def test_distribute_facts_empty_facts(sample_agents):
    """ファクトが空の場合 → 各エージェントに空リスト."""
    result = distribute_facts_to_agents(sample_agents, [], max_per_agent=5)
    for idx in range(len(sample_agents)):
        assert result[idx] == []


def test_distribute_facts_empty_agents():
    """エージェントが空の場合 → 空の dict."""
    result = distribute_facts_to_agents([], [{"fact": "test", "source": "src", "date": "2024-12", "category": "economy", "relevance_keywords": ["test"]}])
    assert result == {}


# ---------------------------------------------------------------------------
# test_distribute_facts_demographic_relevance
# ---------------------------------------------------------------------------

def test_distribute_facts_demographic_relevance(sample_agents, sample_facts):
    """occupation="農業従事者" のエージェントには農業関連ファクトが優先配布される."""
    # sample_agents[1] が農業従事者
    result = distribute_facts_to_agents(sample_agents, sample_facts, max_per_agent=2)
    farmer_facts = result[1]  # agent index 1 = 農業従事者
    # 農業関連ファクトが含まれているべき
    agriculture_facts = [
        f for f in farmer_facts
        if f.get("category") == "agriculture" or "農業" in f.get("relevance_keywords", [])
    ]
    assert len(agriculture_facts) >= 1


def test_distribute_facts_non_agriculture_agent_gets_economy(sample_agents, sample_facts):
    """occupation="会社員" のエージェントには経済関連ファクトが優先配布される."""
    result = distribute_facts_to_agents(sample_agents, sample_facts, max_per_agent=2)
    office_facts = result[0]  # agent index 0 = 会社員
    # 経済関連ファクトが含まれているべき
    economy_facts = [
        f for f in office_facts
        if f.get("category") == "economy"
    ]
    assert len(economy_facts) >= 1


# ---------------------------------------------------------------------------
# test_grounding_fact_has_required_fields
# ---------------------------------------------------------------------------

def test_grounding_fact_has_required_fields(grounding_dir):
    """返却される各ファクトに fact, source, date が非空であること."""
    result = load_grounding_facts("賃金", grounding_dir=grounding_dir)
    assert len(result) >= 1
    for fact in result:
        assert "fact" in fact
        assert "source" in fact
        assert "date" in fact
        assert fact["fact"]  # 非空
        assert fact["source"]  # 非空
        assert fact["date"]  # 非空


def test_grounding_fact_has_category_and_keywords(grounding_dir):
    """返却される各ファクトに category と relevance_keywords が含まれる."""
    result = load_grounding_facts("雇用", grounding_dir=grounding_dir)
    assert len(result) >= 1
    for fact in result:
        assert "category" in fact
        assert "relevance_keywords" in fact
        assert isinstance(fact["relevance_keywords"], list)


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

def test_load_facts_nonexistent_dir():
    """存在しないディレクトリを渡すと空リスト（エラーにならない）."""
    result = load_grounding_facts("テスト", grounding_dir="/nonexistent/path/xyz")
    assert result == []


def test_load_facts_empty_dir(tmp_path):
    """YAML ファイルのない空ディレクトリ → 空リスト."""
    result = load_grounding_facts("テスト", grounding_dir=tmp_path)
    assert result == []


def test_load_facts_malformed_yaml(tmp_path):
    """不正な YAML ファイルがあってもクラッシュしない."""
    bad_file = tmp_path / "bad.yaml"
    bad_file.write_text("this: is: not: valid: yaml: {{{{")
    good_data = {
        "facts": [
            {
                "fact": "有効なファクト",
                "source": "有効な出典",
                "date": "2024-12",
                "category": "test",
                "relevance_keywords": ["テスト"],
            }
        ]
    }
    (tmp_path / "good.yaml").write_text(yaml.dump(good_data, allow_unicode=True))
    # 不正ファイルをスキップして有効なファクトが返る
    result = load_grounding_facts("テスト", grounding_dir=tmp_path)
    assert isinstance(result, list)


def test_load_facts_yaml_without_facts_key(tmp_path):
    """facts キーのない YAML → そのファイルをスキップして空リスト."""
    (tmp_path / "no_facts.yaml").write_text(yaml.dump({"data": []}, allow_unicode=True))
    result = load_grounding_facts("テスト", grounding_dir=tmp_path)
    assert result == []


def test_distribute_facts_max_per_agent_larger_than_facts(sample_agents):
    """max_per_agent がファクト数より多い → 全ファクトを配布."""
    few_facts = [
        {
            "fact": "ファクト1",
            "source": "出典1",
            "date": "2024-12",
            "category": "economy",
            "relevance_keywords": ["経済"],
        }
    ]
    result = distribute_facts_to_agents(sample_agents, few_facts, max_per_agent=10)
    for idx in range(len(sample_agents)):
        assert len(result[idx]) <= len(few_facts)

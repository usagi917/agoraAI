from copy import deepcopy

from src.app.services.society.population_voice import generate_population_voices


def _agent(agent_id: str, index: int, *, speech_style: str = "率直で簡潔") -> dict:
    return {
        "id": agent_id,
        "agent_index": index,
        "speech_style": speech_style,
        "life_event": "転職したばかり",
        "demographics": {"age": 28 + index, "occupation": "会社員"},
    }


def _change(agent_id: str, index: int, stance: str = "賛成") -> dict:
    return {"agent_index": index, "agent_id": agent_id, "stance": stance, "opinion": 0.8}


def test_same_input_and_seed_is_deterministic():
    agents = {"a0": _agent("a0", 0), "a1": _agent("a1", 1)}
    changes = [_change("a0", 0), _change("a1", 1, "反対")]
    kwargs = {"round_index": 2, "prev_stances": {"a0": "中立"}, "seed": 42}

    assert generate_population_voices(changes, agents, **kwargs) == generate_population_voices(
        changes, agents, **kwargs
    )


def test_empty_changes_and_max_voices_limit():
    agents = {f"a{i}": _agent(f"a{i}", i) for i in range(10)}
    changes = [_change(f"a{i}", i) for i in range(10)]

    assert generate_population_voices([], agents, round_index=0) == []
    assert len(generate_population_voices(changes, agents, round_index=0, max_voices=3)) == 3


def test_payload_has_exact_contract_and_age_bracket():
    voices = generate_population_voices(
        [_change("a0", 0)], {"a0": _agent("a0", 0)}, round_index=0, seed=1
    )

    assert set(voices[0]) == {
        "agent_id", "agent_index", "comment", "stance", "prev_stance", "occupation", "age_bracket"
    }
    assert voices[0]["age_bracket"] == "18-29"
    assert voices[0]["occupation"] == "会社員"


def test_speech_style_changes_template_family():
    base = _agent("a0", 0, speech_style="率直で簡潔")
    other = deepcopy(base)
    other["speech_style"] = "分析的で論理的"
    change = [_change("a0", 0)]

    direct = generate_population_voices(change, {"a0": base}, round_index=1, seed=7)
    analytical = generate_population_voices(change, {"a0": other}, round_index=1, seed=7)

    assert direct == generate_population_voices(change, {"a0": base}, round_index=1, seed=7)
    assert direct[0]["comment"] != analytical[0]["comment"]


def test_round_robin_samples_multiple_stances():
    stances = ["賛成"] * 8 + ["中立", "反対"]
    agents = {f"a{i}": _agent(f"a{i}", i) for i in range(len(stances))}
    changes = [_change(f"a{i}", i, stance) for i, stance in enumerate(stances)]

    voices = generate_population_voices(changes, agents, round_index=0, max_voices=3, seed=4)

    assert len({voice["stance"] for voice in voices}) == 3


def test_missing_agent_is_skipped_safely():
    voices = generate_population_voices(
        [_change("missing", 0), _change("known", 1)],
        {"known": _agent("known", 1)},
        round_index=0,
    )

    assert [voice["agent_id"] for voice in voices] == ["known"]


def test_prev_stance_is_reflected_or_none():
    agents = {"a0": _agent("a0", 0), "a1": _agent("a1", 1)}
    changes = [_change("a0", 0), _change("a1", 1, "反対")]

    voices = generate_population_voices(
        changes, agents, round_index=0, prev_stances={"a0": "中立"}, seed=3
    )
    by_id = {voice["agent_id"]: voice for voice in voices}

    assert by_id["a0"]["prev_stance"] == "中立"
    assert by_id["a1"]["prev_stance"] is None


def test_unknown_speech_style_uses_fallback():
    agent = _agent("a0", 0, speech_style="未知の話し方")
    voice = generate_population_voices(
        [_change("a0", 0)], {"a0": agent}, round_index=0, seed=2
    )[0]

    assert voice["comment"]


"""抽取器测试：LLM 与图客户端全部 monkeypatch，无网络。"""
import app.graph.extractor as emod


def test_extract_triples_parses_llm_json(monkeypatch):
    from app.graph.extractor import extract_triples

    monkeypatch.setattr(emod, "chat_completion", lambda system, user, temperature=0.3: """
```json
[{"source":"四君子汤","relation":"组成","target":"人参","source_type":"方剂","target_type":"中药"}]
```
""")
    triples = extract_triples("四君子汤由人参组成。")
    assert triples == [{"source": "四君子汤", "relation": "组成", "target": "人参",
                        "source_type": "方剂", "target_type": "中药"}]


def test_extract_triples_returns_empty_on_bad_llm_output(monkeypatch):
    from app.graph.extractor import extract_triples

    monkeypatch.setattr(emod, "chat_completion", lambda system, user, temperature=0.3: "抱歉，我无法处理。")
    assert extract_triples("随便什么") == []


def test_extract_triples_returns_empty_on_llm_error(monkeypatch):
    from app.graph.extractor import extract_triples

    def boom(system, user, temperature=0.3):
        raise RuntimeError("LLM 不可用")

    monkeypatch.setattr(emod, "chat_completion", boom)
    assert extract_triples("内容") == []


def test_save_candidates_writes_candidate_status(monkeypatch):
    from app.graph.extractor import save_candidates

    calls = []

    class FakeGraph:
        def execute_write(self, cypher, **params):
            calls.append((cypher, params))

    triples = [{"source": "四君子汤", "relation": "组成", "target": "人参",
                "source_type": "方剂", "target_type": "中药"}]
    n = save_candidates(triples, source_doc="内科讲义.md", graph=FakeGraph())

    assert n == 1
    node_cyphers = [c for c, _ in calls if "MERGE (n:" in c]
    edge_cyphers = [c for c, _ in calls if "-[r:" in c or "MATCH (a" in c]
    assert any("status='候选'" in c or "status = '候选'" in c for c, _ in calls)
    assert len(node_cyphers) >= 2 and len(edge_cyphers) == 1
    assert all(p.get("source_doc") in (None, "内科讲义.md") for _, p in calls if p)
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


def test_save_candidates_sets_node_type_property(monkeypatch):
    """C2：节点 MERGE 需写 n.type（供 search?type= 筛选与前端 6 类着色），既有节点用 COALESCE 补齐。"""
    from app.graph.extractor import save_candidates

    calls = []

    class FakeGraph:
        def execute_write(self, cypher, **params):
            calls.append((cypher, params))

    save_candidates([{"source": "补中益气汤", "relation": "主治", "target": "脾胃气虚证",
                      "source_type": "方剂", "target_type": "证候"}],
                    source_doc="内科讲义.md", graph=FakeGraph())

    node_calls = [(c, p) for c, p in calls if "MERGE (n:" in c]
    assert len(node_calls) == 2
    for cypher, _ in node_calls:
        assert "n.type = $type" in cypher                     # ON CREATE 写入 type
        assert "n.type = COALESCE(n.type, $type)" in cypher   # ON MATCH 补齐、不覆盖
    types = {p["name"]: p["type"] for _, p in node_calls}
    assert types == {"补中益气汤": "方剂", "脾胃气虚证": "证候"}


def test_save_candidates_preserves_published_on_match(monkeypatch):
    from app.graph.extractor import save_candidates

    calls = []

    class FakeGraph:
        def execute_write(self, cypher, **params):
            calls.append(cypher)

    save_candidates([{"source": "四君子汤", "relation": "组成", "target": "人参",
                      "source_type": "方剂", "target_type": "中药"}],
                    source_doc="x.md", graph=FakeGraph())
    edge_cypher = next(c for c in calls if "MERGE (a)-[r:" in c)
    assert "CASE WHEN r.status = '已发布' THEN '已发布'" in edge_cypher
    assert "ELSE '候选'" in edge_cypher


def test_extract_triples_drops_illegal_relation_and_type(monkeypatch):
    import app.graph.extractor as emod

    monkeypatch.setattr(emod, "chat_completion", lambda system, user, temperature=0.3: """
[{"source":"A","relation":"治疗","target":"B","source_type":"方剂","target_type":"中药"},
 {"source":"C","relation":"组成","target":"D","source_type":"病名","target_type":"中药"},
 {"source":"E","relation":"组成","target":"F","source_type":"方剂","target_type":"中药"}]
""")
    out = emod.extract_triples("x")
    assert len(out) == 1 and out[0]["source"] == "E"
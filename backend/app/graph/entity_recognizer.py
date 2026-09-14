"""实体识别：基于图谱词表的词典最长匹配（阶段 3 由 LLM query_understand 取代）。

vocab 来自 GraphClient.all_entities()：每个 {name, alias, type}，
alias 以顿号分隔（如 "园参、山参"）。
"""
from collections.abc import Iterable


def recognize_entities(question: str, vocab: Iterable[dict]) -> list[dict]:
    term_map: dict[str, dict] = {}
    for v in vocab:
        for c in [v["name"], *(p.strip() for p in (v["alias"] or "").split("、") if p.strip())]:
            if c:                       # 主名先注册；别名与主名同串时保留主名（取先注册）
                term_map.setdefault(c, v)

    hits: list[dict] = []
    i, n = 0, len(question)
    while i < n:
        hit = None
        for j in range(n, i, -1):       # 该位置最长优先
            v = term_map.get(question[i:j])
            if v is not None:
                hit = (question[i:j], v)
                break
        if hit is None:
            i += 1
            continue
        term, v = hit
        hits.append({"name": v["name"], "type": v["type"], "matched": term})
        i += len(term)

    seen: set[str] = set()
    ordered: list[dict] = []
    for h in hits:
        if h["name"] not in seen:
            seen.add(h["name"])
            ordered.append(h)
    return ordered
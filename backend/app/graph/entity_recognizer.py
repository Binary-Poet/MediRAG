"""实体识别：基于图谱词表的词典最长匹配（阶段 3 由 LLM query_understand 取代）。

vocab 来自 GraphClient.all_entities()：每个 {name, alias, type}，
alias 以顿号分隔（如 "园参、山参"）。
"""
from collections.abc import Iterable


def recognize_entities(question: str, vocab: Iterable[dict]) -> list[dict]:
    terms: list[tuple[str, dict]] = []
    for v in vocab:
        cands = [v["name"], *(p.strip() for p in (v["alias"] or "").split("、") if p.strip())]
        terms.extend((c, v) for c in cands if c)
    # 最长优先，避免短词先占位截断长词（如"发热重微恶风" vs "发热"）
    terms.sort(key=lambda t: -len(t[0]))

    hits: list[dict] = []
    covered = [False] * len(question)
    for term, v in terms:
        start = 0
        while True:
            idx = question.find(term, start)
            if idx < 0:
                break
            if not any(covered[idx: idx + len(term)]):
                for i in range(idx, idx + len(term)):
                    covered[i] = True
                hits.append({"name": v["name"], "type": v["type"], "matched": term})
            start = idx + 1

    seen: set[str] = set()
    ordered: list[dict] = []
    for h in hits:  # 按原文顺序归并（别名命中归顺到主名）
        if h["name"] not in seen:
            seen.add(h["name"])
            ordered.append(h)
    return ordered
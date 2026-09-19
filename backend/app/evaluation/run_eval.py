"""阶段 6 离线评测脚本。

职责（对应《MediRAG-合并改造方案.md》6.8）：
1. 消融实验：纯向量 / 向量+关键词(RRF) / 三路(+图谱) 在 Golden QA 上的 Recall@K 与 MRR，
   证明多路融合有效——简历量化数字来源，必须实测。
2. RAGAS 三指标：faithfulness / answer relevancy / context precision，
   用三路融合证据组装 answer_cn_tcm Prompt 生成答案后评测（真实 DeepSeek + SiliconFlow）。
3. 兜底率：拒答类样本正确触发拒答的比例。
4. bad case：低于设定阈值的样本归档，供一轮迭代对比。

运行（需 Neo4j + 真实 LLM/Embedding API key，位于 backend/ 下）：
    python -m app.evaluation.run_eval --limit 8      # 小样本冒烟
    python -m app.evaluation.run_eval --ragas        # 全量检索 + RAGAS
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

# data/eval 位于项目根（backend/app/evaluation 的上三级）
PROJECT_ROOT = Path(__file__).resolve().parents[3]
EVAL_DIR = PROJECT_ROOT / "data" / "eval"
GOLDEN = EVAL_DIR / "golden_qa.jsonl"
OUT_DIR = EVAL_DIR / "output"
BAD_CASE_DIR = EVAL_DIR / "bad_cases"

sys.stdout.reconfigure(encoding="utf-8")


# ============ 命中判定 ============
def _expand_fact(fact: str) -> tuple[str, str, str] | None:
    """把 golden fact 拆成 (source, relation, target)；非三元组返回 None。

    golden 事实格式如「四君子汤 -组成-> 人参」，箭头即 `-{rel}-> `。
    """
    for rel in ("组成", "主治", "功效", "禁忌", "表现"):
        marker = f"-{rel}-> "
        if marker in fact:
            src, rest = fact.split(marker, 1)
            return src.strip(), rel, rest.strip()
    return None


def _fact_hit(fact: str, evidence: list[dict], graph_facts: list[dict]) -> bool:
    """判断某条 golden fact 是否被给定证据命中。

    - 图谱三元组「A -关系-> B」：优先精确匹配图库返回的 (source, relation, target)，
      否则要求 A 与 B 同时出现在某条证据文本中（连接成立的宽松判定）。
    - 普通要点词串：要求整串作为子串出现在某证据文本里。
    """
    triple = _expand_fact(fact)
    if triple:
        src, rel, tgt = triple
        if any(
            f.get("source") == src and f.get("relation") == rel and f.get("target") == tgt
            for f in graph_facts
        ):
            return True
        texts = [e["text"] for e in evidence] + [f"{f.get('source','')}{f.get('relation','')}{f.get('target','')}" for f in graph_facts]
        return any(src in t and tgt in t for t in texts)
    return any(fact in e["text"] for e in evidence)


# ============ 三路检索（消融用，直接用底层组件，不依赖 Agent 状态机） ============
def retrieve(mode: str, question: str, top_k: int = 5,
             settings_override=None) -> tuple[list[dict], list[dict]]:
    """返回 (evidence, graph_facts)。mode ∈ {vector, vector+keyword, three}。"""
    from app.config import get_settings
    from app.graph.neo4j_client import get_graph
    from app.llm.embedding import embed_texts
    from app.llm.rerank import rerank
    from app.retrieval.keyword import get_keyword_index
    from app.retrieval.rrf import rrf_fuse
    from app.retrieval.vector_store import get_store

    s = get_settings()
    store = get_store()
    kw = get_keyword_index()

    vector_hits = store.search(embed_texts([question])[0], top_k=s.semantic_k)
    keyword_hits = kw.search(question, top_k=s.keyword_k) if mode in ("vector+keyword", "three") else []

    graph_facts: list[dict] = []
    if mode == "three":
        # 实体取全库已发布节点名中命中题意者；用 1~2 跳邻居覆盖全部关系，
        # 不走 directed_paths 定向模板：formula_mechanism 模板 RETURN 无 relation 列，
        # directed_paths 会 KeyError 而 abort（见 graph/neo4j_client.py 既有缺陷）。
        try:
            names = [e["name"] for e in get_graph().all_entities() if e["name"] in question]
            graph_facts = get_graph().neighbors(names, hop=2) or []
        except Exception as exc:  # 图谱不可用不应中断整轮消融
            print(f"  [图谱不可用] {exc}", file=sys.stderr)

    # 融合：向量 + 关键词走 RRF；三路时再把图谱事实作为额外证据并入候选集
    if mode == "vector":
        fused = vector_hits
    else:
        fused = rrf_fuse([vector_hits, keyword_hits or []], k=s.rrf_k)

    if fused:
        docs = [e["text"] for e in fused][:s.fuse_candidate]
        reranked = rerank(question, docs, top_n=top_k)
        evidence = [dict(fused[r["index"]], rerank_score=r["score"]) for r in reranked]
    else:
        evidence = []

    # 三路由图谱事实补齐不足：融合证据不足 top_k 时，把图谱事实转成伪证据
    if mode == "three" and graph_facts:
        seen = {e.get("chunk_id") for e in evidence}
        for f in graph_facts:
            if len(evidence) >= top_k:
                break
            text = f"{f.get('source','')} {f.get('relation','')} {f.get('target','')}"
            if text not in seen:
                evidence.append({"chunk_id": f"graph:{f.get('source')}{f.get('relation')}{f.get('target')}",
                                 "text": text, "doc_name": "图谱", "source": "graph"})
                seen.add(text)
    return evidence[:top_k], graph_facts


def _evidence_texts(evidence: list[dict]) -> list[str]:
    """转成 RAGAS 的 retrieved_contexts。"""
    return [e["text"] for e in evidence]


# ============ 答案生成（复用生产 Prompt） ============
def build_prompt(question: str, evidence: list[dict], graph_facts: list[dict]) -> str:
    from app.agent.nodes.context import PROMPTS_DIR, ANSWER_TEMPLATE
    _ = PROMPTS_DIR
    graph_block = "\n".join(
        f"{f['source']} --{f['relation']}--> {f['target']}" for f in graph_facts) or "（无）"
    evidence_block = "\n\n".join(
        f"[{i}] 《{e.get('doc_name','')}》{e.get('chapter','')}（序号 {e.get('page_no','')}）\n{e['text']}"
        for i, e in enumerate(evidence)) or "（无）"
    template = ANSWER_TEMPLATE.read_text(encoding="utf-8")
    return template.format(graph_facts=graph_block, evidence=evidence_block, question=question)


def generate_answer(question: str, evidence: list[dict], graph_facts: list[dict]) -> str:
    from app.llm.chat import chat_completion
    prompt = build_prompt(question, evidence, graph_facts)
    return chat_completion("你是中医药知识助手「本草智问」", prompt, temperature=0.3)


# ============ 检索指标 ============
def retrieval_metrics(qa_list: list[dict], mode: str) -> dict:
    hits_all, mrr_all, n = [], [], 0
    for qa in qa_list:
        if qa["category"] == "拒答":
            continue
        ev, gf = retrieve(mode, qa["question"])
        facts = qa.get("expected_facts") or []
        hit_pos = None
        hit_count = 0
        # 按证据顺序逐个判定，取首个命中位置（复数事实：任一命中即算该问题有召回，MRR 用首个命中）
        positions = [i + 1 for i, e in enumerate(ev) if any(_fact_hit(f, ev[: i + 1], gf) for f in facts)]
        hit_any = len(positions) > 0
        hits_all.append(1.0 if hit_any else 0.0)
        mrr_all.append(1.0 / positions[0] if positions else 0.0)
        n += 1
    recall = sum(hits_all) / n if n else 0.0
    mrr = sum(mrr_all) / n if n else 0.0
    return {"mode": mode, "n": n, "recall_at_k": round(recall, 4), "mrr": round(mrr, 4)}


# ============ 兜底率（拒答类） ============
def fallback_rate(qa_list: list[dict]) -> dict:
    err = sys.stderr
    _ = err
    from app.retrieval.vector_store import get_store
    from app.llm.embedding import embed_texts
    from app.retrieval.keyword import get_keyword_index
    from app.llm.rerank import rerank
    from app.retrieval.rrf import rrf_fuse
    from app.config import get_settings

    s = get_settings()
    store = get_store()
    kw = get_keyword_index()
    rejects = [q for q in qa_list if q["category"] == "拒答"]
    if not rejects:
        return {"reject_n": 0, "fallback_rate": None}
    triggered = 0
    for q in rejects:
        v = store.search(embed_texts([q["question"]])[0], top_k=s.semantic_k)
        k = kw.search(q["question"], top_k=s.keyword_k)
        fused = rrf_fuse([v, k], k=s.rrf_k)
        # 兜底三条件：无候选 或 精排 top 过匀分不达阈值 或 判定为拒答类已无证据
        if not fused:
            triggered += 1
            continue
        docs = [e["text"] for e in fused][:s.fuse_candidate]
        rr = rerank(q["question"], docs, top_n=1)
        top = rr[0]["score"] if rr else 0.0
        if top < s.evidence_min_score:
            triggered += 1
    return {"reject_n": len(rejects), "fallback_rate": round(triggered / len(rejects), 4)}


# ============ RAGAS 三指标 ============
def ragas_eval(qa_list: list[dict], mode: str, limit: int) -> dict:
    from app.config import get_settings
    s = get_settings()
    samples_q = [q for q in qa_list if q["category"] != "拒答"][:limit]
    rows = []
    for q in samples_q:
        ev, gf = retrieve(mode, q["question"])
        ans = generate_answer(q["question"], ev, gf)
        rows.append({"user_input": q["question"], "reference": q["ground_truth"],
                     "retrieved_contexts": _evidence_texts(ev), "response": ans,
                     "category": q["category"]})

    # ragas 0.4.3 在 langchain 1.4 下会 import langchain_community.chat_models.vertexai，
    # 该子模块在新版 langchain_community 已拆到 langchain_google_vertexai。artificial shim：
    # 仅满足 provider 注册导入（评测用 DeepSeek，不实例化 ChatVertexAI）。
    import sys as _sys
    import types as _types
    _shim_name = "langchain_community.chat_models.vertexai"
    if _shim_name not in _sys.modules:
        try:
            from langchain_google_vertexai import ChatVertexAI  # noqa: F401
        except Exception:
            ChatVertexAI = object  # type: ignore[assignment]
        _m = _types.ModuleType(_shim_name)
        _m.ChatVertexAI = ChatVertexAI  # type: ignore[attr-defined]
        _sys.modules[_shim_name] = _m

    try:
        import ragas  # noqa: F401
        from ragas import EvaluationDataset, SingleTurnSample, evaluate
        from ragas.metrics import AnswerRelevancy, ContextPrecision, Faithfulness
    except Exception as exc:  # RAGAS 依赖冲突同类报错统一收敛
        return {"error": f"RAGAS 不可用：{exc}"}

    from langchain_openai import ChatOpenAI, OpenAIEmbeddings

    llm = ChatOpenAI(
        model=s.llm_model_main,
        api_key=s.deepseek_api_key,
        base_url=s.deepseek_base_url,
        temperature=0.3,
    )
    emb = OpenAIEmbeddings(
        model=s.embed_model,
        api_key=s.siliconflow_api_key,
        base_url=s.siliconflow_base_url,
    )
    dataset = EvaluationDataset(samples=[
        SingleTurnSample(user_input=r["user_input"], reference=r["reference"],
                         retrieved_contexts=r["retrieved_contexts"], response=r["response"])
        for r in rows
    ])
    result = evaluate(dataset=dataset, metrics=[Faithfulness(), AnswerRelevancy(), ContextPrecision()],
                      llm=llm, embeddings=emb)
    # ragas 0.4.x：evaluate 返回 RagasResult，指标列在 .to_pandas() 中聚合取均值
    try:
        df = result.to_pandas()
    except AttributeError:  # 兼容早期版本：直接按 (sample, score) 对解析
        scores: dict = {metric.name.lower(): round(sum(s[1] for s in v) / len(v), 4)
                        for metric, v in result.scores}
        return {mode: scores, "samples": rows}
    scores = {}
    for col in df.columns:
        low = col.lower()
        if any(k in low for k in ("faithfulness", "answer_relevancy", "context_precision")):
            try:
                scores[col] = round(float(df[col].mean()), 4)
            except (TypeError, ValueError):
                scores[col] = None
    return {mode: scores, "samples": rows}


# ============ bad case 归档 ============
def archive_bad_cases(qa_list: list[dict], mode: str, recall_threshold: float = 0.5) -> list[dict]:
    bad = []
    for q in qa_list:
        if q["category"] == "拒答":
            continue
        ev, gf = retrieve(mode, q["question"])
        if not any(_fact_hit(f, ev, gf) for f in q.get("expected_facts") or []):
            bad.append({"question": q["question"], "category": q["category"],
                        "expected_facts": q["expected_facts"], "retrieved": [e["text"] for e in ev]})
    if bad:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        d = BAD_CASE_DIR / mode / ts
        d.mkdir(parents=True, exist_ok=True)
        (d / "bad_cases.json").write_text(json.dumps(bad, ensure_ascii=False, indent=2), encoding="utf-8")
    return bad


# ============ main ============
def load_golden() -> list[dict]:
    if not GOLDEN.exists():
        raise FileNotFoundError(f"缺少评测集：{GOLDEN}")
    return [json.loads(ln) for ln in GOLDEN.read_text(encoding="utf-8").splitlines()
            if ln.strip() and not ln.lstrip().startswith("#")]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="限制参与数量（0=全量）")
    ap.add_argument("--ragas", action="store_true", help="额外跑 RAGAS 三指标")
    ap.add_argument("--mode", default="three", choices=("vector", "vector+keyword", "three"))
    args = ap.parse_args()

    qa = load_golden()
    if args.limit:
        qa = qa[: args.limit]
    print(f"评测集加载完成：{len(qa)} 条")
    from collections import Counter
    print("分布：", dict(Counter(q["category"] for q in qa)))

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    report: dict = {"ts": datetime.now().isoformat(timespec="seconds"),
                    "golden_n": len(qa), "results": {}, "fallback": {}, "ragas": None,
                    "modes": []}

    # 消融：三个 mode 同集跑 recall/mrr
    for mode in ("vector", "vector+keyword", "three"):
        print(f"\n[消融] mode={mode}")
        rm = retrieval_metrics(qa, mode)
        report["results"][mode] = rm
        report["modes"].append(mode)
        print(f"  {rm}")

    print("\n[兜底率]")
    report["fallback"] = fallback_rate(qa)
    print(f"  {report['fallback']}")

    if args.ragas:
        print("\n[RAGAS 三指标] mode=three（需真实 LLM/Embedding，耗时较长）")
        report["ragas"] = ragas_eval(qa, "three", args.limit or len(qa))

    # 三路 bad case 归档
    bad = archive_bad_cases(qa, "three")
    report["bad_case_n"] = len(bad)
    print(f"\n三路召回 bad case 数：{len(bad)}（已归档 {BAD_CASE_DIR}）")
    for b in bad[:5]:
        print(f"  - [{b['category']}] {b['question']}")

    out = OUT_DIR / f"eval_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n报告已写入：{out}")


if __name__ == "__main__":
    main()
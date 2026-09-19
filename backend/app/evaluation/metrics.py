"""评测数字真源：解析 run_eval 最近的输出，统一呈现消融 + RAGAS + 兜底数字。

职责边界：
- 在线指标的实时聚合由 api/stats.py 承担（读 feedback / retrieval_log 真实数据），
  本模块不重复。
- 本模块只读 run_eval.py 写出的离线评测产物（data/eval/output/eval_*.json），
  提供"最近一次实测数字"的一站式入口，供 README、简历、运行概览、后续迭代对照引用，
  保证"简历数字必须来自实测"有可追踪真源。

用法：python -m app.evaluation.metrics
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# 项目根（backend/app/evaluation 的上三级）
PROJECT_ROOT = Path(__file__).resolve().parents[3]
EVAL_OUT = PROJECT_ROOT / "data" / "eval" / "output"


def _latest_run_file() -> Path | None:
    files = sorted(EVAL_OUT.glob("eval_*.json")) if EVAL_OUT.exists() else []
    return files[-1] if files else None


def load_latest() -> dict | None:
    f = _latest_run_file()
    if not f:
        return None
    return json.loads(f.read_text(encoding="utf-8"))


def summarize() -> dict:
    """把最近一次评测输出收敛成可写进 README/简历的标准字段。"""
    run = load_latest()
    if not run:
        return {"source": None, "error": "data/eval/output 下暂无评测报告，请先运行 run_eval.py"}
    abl = run.get("results", {})
    recall = {m: abl[m]["recall_at_k"] for m in ("vector", "vector+keyword", "three") if m in abl}
    mrr = {m: abl[m]["mrr"] for m in ("vector", "vector+keyword", "three") if m in abl}
    ragas = run.get("ragas") or {}
    ragas_scores = ragas.get("three") if isinstance(ragas, dict) else None
    return {
        "source": _latest_run_file().name if _latest_run_file() else None,
        "ts": run.get("ts"),
        "golden_n": run.get("golden_n"),
        "recall_at_5": recall,
        "mrr": mrr,
        "ragas": ragas_scores,
        "fallback_rate": (run.get("fallback") or {}).get("fallback_rate"),
        "bad_case_n": run.get("bad_case_n"),
    }


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(summarize(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
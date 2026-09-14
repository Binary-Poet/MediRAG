"""语料解析测试：验证 tcm_corpus.md 切片数量与元数据提取。"""
from pathlib import Path

from app.ingestion.pipeline import DEFAULT_CORPUS, load_corpus


def test_corpus_has_expected_chunks() -> None:
    chunks = load_corpus()
    # 语料含 11 个 ### 词条（3 方剂 + 3 证候 + 5 中药）
    assert len(chunks) == 11
    assert DEFAULT_CORPUS.exists()


def test_chunk_metadata_fields() -> None:
    chunks = {c["title"]: c for c in load_corpus()}

    first = chunks["四君子汤"]
    assert first["doc_name"] == "中药方剂学基础"
    assert first["chapter"] == "第1节"
    assert first["page_no"] == 1
    assert first["chunk_id"] == "中药方剂学基础#0001"
    assert "人参" in first["text"]
    assert first["topic"] == "综合典籍"

    # 金匮要略条文
    suanzao = chunks["酸枣仁汤"]
    assert suanzao["doc_name"] == "《金匮要略》虚劳篇"
    assert suanzao["page_no"] == 3

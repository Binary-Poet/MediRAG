"""切片器测试：元数据完整性、chunk_id 唯一、PDF 页码推进。"""
from app.ingestion.splitter import MAX_CHUNK_CHARS, split_text


def test_plain_text_split_with_metadata():
    chunks = split_text("四君子汤组成。\n\n归脾汤组成。" , doc_name="内科讲义.md", topic="内科")
    assert len(chunks) == 1                      # 两段合并未超长
    c = chunks[0]
    assert c["chunk_id"] == "内科讲义.md#0000"
    assert c["doc_name"] == "内科讲义.md"
    assert c["topic"] == "内科"
    assert c["page_no"] == 1
    assert "四君子汤" in c["text"]


def test_long_text_splits_into_multiple_chunks_with_unique_ids():
    para = "人参大补元气补脾益肺。"
    text = "\n\n".join([para] * 200)
    chunks = split_text(text, doc_name="中药学.md", topic="内科")
    assert len(chunks) > 1
    ids = [c["chunk_id"] for c in chunks]
    assert len(ids) == len(set(ids))             # 唯一
    assert all(len(c["text"]) <= MAX_CHUNK_CHARS + 50 for c in chunks)
    assert [c["page_no"] for c in chunks] == list(range(1, len(chunks) + 1))


def test_pdf_page_marker_advances_page_no():
    text = "第一页内容。\f第二页内容。"
    chunks = split_text(text, doc_name="伤寒论.pdf", topic="内科")
    pages = {c["page_no"] for c in chunks}
    assert pages == {1, 2}
    assert any("第二页" in c["text"] and c["page_no"] == 2 for c in chunks)


def test_base_seq_offsets_chunk_id():
    chunks = split_text("内容。", doc_name="x.md", topic="内科", base_seq=7)
    assert chunks[0]["chunk_id"] == "x.md#0007"


def test_blank_text_returns_empty():
    assert split_text("   \n  ", doc_name="x.md", topic="内科") == []
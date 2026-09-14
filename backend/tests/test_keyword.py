"""关键词检索测试：jieba + rank-bm25 排序与过滤。"""
from app.retrieval.keyword import KeywordIndex

CHUNKS = [
    {"chunk_id": "a", "title": "四君子汤", "text": "由人参、白术、茯苓、炙甘草组成，益气健脾", "doc_name": "x", "chapter": "c", "page_no": 1, "topic": "综合典籍"},
    {"chunk_id": "b", "title": "人参", "text": "大补元气、补脾益肺，为补气要药", "doc_name": "y", "chapter": "c", "page_no": 2, "topic": "综合典籍"},
    {"chunk_id": "c", "title": "茯苓", "text": "利水渗湿、健脾宁心", "doc_name": "z", "chapter": "c", "page_no": 3, "topic": "综合典籍"},
]


def test_search_returns_ranked_hits():
    idx = KeywordIndex()
    assert idx.build(CHUNKS) == 3

    hits = idx.search("四君子汤 人参", top_k=3)

    assert hits and hits[0]["chunk_id"] == "a"  # 同时命中两个词
    assert all("score" in h for h in hits)
    assert all(h["doc_name"] for h in hits)  # metadata 完整透传


def test_search_zero_score_filtered():
    idx = KeywordIndex()
    idx.build(CHUNKS)

    hits = idx.search("天气", top_k=3)  # 完全不相关的词，jieba 无命中词

    assert hits == []


def test_search_unbuilt_returns_empty():
    assert KeywordIndex().search("人参") == []
"""实体识别测试：词典匹配 / 别名命中 / 最长优先 / 去重 / 跳过重叠。"""
from app.graph.entity_recognizer import recognize_entities

VOCAB = [
    {"name": "四君子汤", "alias": "", "type": "方剂"},
    {"name": "当归", "alias": "", "type": "中药"},
    {"name": "鹿角胶", "alias": "", "type": "中药"},
    {"name": "人参", "alias": "园参、山参", "type": "中药"},
    {"name": "发热重微恶风", "alias": "", "type": "症状"},
]


def test_matches_exact_name():
    hits = recognize_entities("四君子汤由哪些中药组成？", VOCAB)
    assert hits == [{"name": "四君子汤", "type": "方剂", "matched": "四君子汤"}]


def test_matches_alias_and_dedups():
    hits = recognize_entities("园参有什么功效？", VOCAB)
    assert hits == [{"name": "人参", "type": "中药", "matched": "园参"}]


def test_longest_match_wins():
    hits = recognize_entities("发热重微恶风怎么缓解", VOCAB)
    assert [h["matched"] for h in hits] == ["发热重微恶风"]


def test_multiple_entities_in_order():
    hits = recognize_entities("当归和人参一起用", VOCAB)
    assert [h["name"] for h in hits] == ["当归", "人参"]


def test_overlapping_terms_take_first_longest():
    # "鹿角胶" 覆盖后，内部不重复命中
    hits = recognize_entities("鹿角胶补什么", VOCAB)
    assert len(hits) == 1 and hits[0]["name"] == "鹿角胶"


def test_no_match_returns_empty():
    assert recognize_entities("今天的天气怎么样", VOCAB) == []
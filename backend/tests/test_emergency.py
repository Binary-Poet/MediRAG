from app.safety.emergency import detect_emergency, EMERGENCY_WORDS


def test_detect_emergency_hits_keyword():
    assert detect_emergency("我胸口疼得厉害怎么用中医药调理") is True


def test_detect_emergency_no_keyword():
    assert detect_emergency("四君子汤由哪些中药组成") is False


def test_emergency_words_contains_required():
    for w in ["胸痛", "昏迷", "大出血", "休克", "孕妇出血"]:
        assert w in EMERGENCY_WORDS
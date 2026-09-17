from app.safety.emergency import detect_emergency, EMERGENCY_WORDS


def test_detect_emergency_hits_keyword():
    assert detect_emergency("我胸口疼得厉害怎么用中医药调理") is True


def test_detect_emergency_no_keyword():
    assert detect_emergency("四君子汤由哪些中药组成") is False


def test_emergency_words_contains_required():
    for w in ["胸痛", "昏迷", "大出血", "休克", "孕妇出血"]:
        assert w in EMERGENCY_WORDS


# ===== 「中风」同形不同义：中医证候名不得判为急症（真实环境实测发现）=====

def test_detect_emergency_ignores_tcm_zhongfeng_pattern_names():
    """太阳中风（表虚证）是桂枝汤主治，与脑卒中同形不同义。

    实测：问「麻黄汤和桂枝汤有什么区别」时反思轮补出「太阳中风证」实体，
    子串匹配命中「中风」→ 整个方剂比较问题弹出 120 急症横幅。
    """
    assert detect_emergency("太阳中风证用什么方剂") is False
    assert detect_emergency("太阳中风") is False
    assert detect_emergency("中风证") is False
    assert detect_emergency("太阳中风表虚证") is False
    assert detect_emergency("麻黄汤和桂枝汤有什么区别 太阳中风证 太阳伤寒证") is False


def test_detect_emergency_still_hits_real_stroke():
    """去掉证候用法后，真·脑卒中仍必须拦截（不得因噎废食）。"""
    assert detect_emergency("老人突然中风了怎么办") is True
    assert detect_emergency("中风") is True
    assert detect_emergency("我怀疑是中风，嘴歪了") is True
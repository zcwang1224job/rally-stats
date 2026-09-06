"""Unit test: match_wins() 達標判定公式（research.md #2）——僅讀取
target_score/cap_score，deuce_threshold 不參與運算，以 001 之 21 分制
（21/20/30）與 15 分制（15/14/21）兩組固定預設值交叉驗證。"""

import pytest

from app.domains.schedule.service import match_wins

# 21 分制：target=21, cap=30
TARGET_21, CAP_30 = 21, 30
# 15 分制：target=15, cap=21
TARGET_15, CAP_21 = 15, 21


@pytest.mark.parametrize(
    ("score_x", "score_y", "target", "cap", "expected"),
    [
        # 21 分制
        (20, 18, TARGET_21, CAP_30, False),  # 未達標
        (21, 19, TARGET_21, CAP_30, True),  # 21:19，領先 2 分達標
        (21, 20, TARGET_21, CAP_30, False),  # 21:20，未領先 2 分（deuce 中）
        (22, 20, TARGET_21, CAP_30, True),  # 22:20，領先 2 分達標
        (29, 29, TARGET_21, CAP_30, False),  # 29:29 未觸及封頂
        (30, 29, TARGET_21, CAP_30, True),  # 30 分封頂，領先僅 1 分仍判勝
        (30, 28, TARGET_21, CAP_30, True),  # 30 分封頂
        # 15 分制
        (15, 13, TARGET_15, CAP_21, True),  # 15:13，領先 2 分達標
        (20, 20, TARGET_15, CAP_21, False),  # 20:20 未觸及封頂
        (21, 20, TARGET_15, CAP_21, True),  # 21 分封頂，領先僅 1 分仍判勝
        (14, 14, TARGET_15, CAP_21, False),  # deuce 中，未達標
        # 自訂模式：target=10, cap=15
        (9, 5, 10, 15, False),
        (10, 8, 10, 15, True),  # 領先 2 分
        (10, 9, 10, 15, False),  # 領先僅 1 分
        (15, 14, 10, 15, True),  # 觸及封頂
    ],
)
def test_match_wins_formula(
    score_x: int, score_y: int, target: int, cap: int, expected: bool
) -> None:
    assert match_wins(score_x, score_y, target, cap) is expected

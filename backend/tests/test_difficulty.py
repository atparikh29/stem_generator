from app.config import settings
from app.schemas.generator import MathTask
from app.verification import difficulty
from app.verification.result import FailureCode

# A 3-term cubic derivative scores difficulty bin 3 under the current heuristic.
_BIN3 = MathTask(kind="derivative", expression="x**3 - 2*x**2 + 5", expected_answer="3*x**2 - 4*x")


def test_score_is_stable():
    assert difficulty.score(_BIN3) == 3


def test_difficulty_is_normalized_per_skill():
    # Each skill spans low->high relative to its OWN complexity range.
    easy_deriv = MathTask(kind="derivative", expression="x**2", expected_answer="2*x")
    hard_deriv = MathTask(kind="derivative", expression="x**5 - 3*x**4 + 2*x**3 - x**2 + 7*x",
                          expected_answer="0")
    assert difficulty.score(easy_deriv) == 1
    assert difficulty.score(hard_deriv) == 5
    # A canonical factorable limit is mid-range, not pinned at the top.
    lim = MathTask(kind="limit", variable="x", expression="(x**2 - 9)/(x - 3)", point=3.0,
                   expected_answer="6")
    assert 1 <= difficulty.score(lim) <= 3


def test_exact_match_passes():
    saved = settings.difficulty_tolerance
    settings.difficulty_tolerance = 0
    try:
        assert difficulty.verify(_BIN3, target=3).passed
    finally:
        settings.difficulty_tolerance = saved


def test_off_by_one_fails_when_strict():
    saved = settings.difficulty_tolerance
    settings.difficulty_tolerance = 0
    try:
        res = difficulty.verify(_BIN3, target=4)  # bin 3 vs target 4
        assert not res.passed
        assert FailureCode.OFF_TARGET_DIFFICULTY in res.failures
    finally:
        settings.difficulty_tolerance = saved


def test_off_by_one_passes_with_tolerance():
    saved = settings.difficulty_tolerance
    settings.difficulty_tolerance = 1
    try:
        assert difficulty.verify(_BIN3, target=4).passed   # |3-4| <= 1
        assert difficulty.verify(_BIN3, target=2).passed   # |3-2| <= 1
        assert not difficulty.verify(_BIN3, target=5).passed  # |3-5| = 2 > 1
    finally:
        settings.difficulty_tolerance = saved

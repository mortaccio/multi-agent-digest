import sys
sys.path.insert(0, 'agents/prioritizer')
from app import score_line

def test_urgent_keyword_scores_one():
    assert score_line("This is urgent") == 1

def test_multiple_keywords_stack():
    assert score_line("Urgent and important deadline") == 3

def test_no_keywords_scores_zero():
    assert score_line("Regular project update") == 0

def test_scoring_is_case_insensitive():
    assert score_line("URGENT DEADLINE ASAP") == 3


def test_error_line_scores_priority():
    assert score_line("CRITICAL error: database timeout exception") >= 4


def test_action_line_scores_priority():
    assert score_line("Action: Investigate payments immediately") >= 1

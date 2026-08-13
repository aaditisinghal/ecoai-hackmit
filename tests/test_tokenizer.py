"""Token estimation.

The estimator is approximate by design, so these assert the properties that
must hold rather than exact counts: monotonicity, sane bounds, and that the
structural cases the old ``len(text)/4`` rule got badly wrong are handled.
"""

from __future__ import annotations

import pytest

from ecoai.services import tokenizer
from ecoai.services.tokenizer import count_tokens, set_token_counter


@pytest.fixture(autouse=True)
def _restore_default_counter():
    yield
    set_token_counter(None)


class TestBasics:
    def test_empty_is_zero(self):
        assert count_tokens("") == 0

    def test_non_empty_is_at_least_one(self):
        assert count_tokens("a") >= 1
        assert count_tokens(".") >= 1

    def test_longer_text_costs_more(self):
        short = count_tokens("Summarize this.")
        long = count_tokens("Summarize this document in exactly three detailed bullet points.")
        assert long > short

    def test_monotonic_under_concatenation(self):
        base = "The quick brown fox jumps over the lazy dog. "
        counts = [count_tokens(base * n) for n in range(1, 6)]
        assert counts == sorted(counts)
        assert len(set(counts)) == 5


class TestStructuralCases:
    """Cases where a flat characters-per-token rule is badly wrong."""

    def test_whitespace_runs_are_cheap(self):
        """40 spaces are not 10 tokens the way len/4 claimed."""
        spaces = count_tokens(" " * 40)
        words = count_tokens("alpha beta gamma delta epsilon zeta eta theta")
        assert spaces < words

    def test_a_single_space_merges_into_its_word(self):
        assert count_tokens(" word") == count_tokens("word")

    def test_short_words_are_one_token(self):
        for word in ["cat", "the", "dog", "run"]:
            assert count_tokens(word) == 1

    def test_long_words_fragment(self):
        assert count_tokens("antidisestablishmentarianism") > 1

    def test_digit_runs_group(self):
        assert count_tokens("1234567890") > 1
        assert count_tokens("42") == 1

    def test_wide_scripts_cost_about_one_token_per_character(self):
        text = "日本語のテキスト"
        assert count_tokens(text) >= len(text) * 0.8


class TestInjectedCounter:
    def test_injected_counter_takes_over(self):
        set_token_counter(lambda text: 999)
        assert count_tokens("anything at all") == 999

    def test_none_restores_the_estimator(self):
        set_token_counter(lambda text: 999)
        set_token_counter(None)
        assert count_tokens("anything at all") != 999

    def test_module_state_is_not_leaked_between_tests(self):
        assert tokenizer._counter is None

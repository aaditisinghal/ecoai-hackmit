"""Prompt optimizer behaviour."""

from __future__ import annotations

import pytest

from ecoai.services.optimizer import Strategy, optimizer


class TestStrategyParsing:
    def test_defaults_to_balanced(self):
        assert Strategy.parse(None) is Strategy.BALANCED
        assert Strategy.parse("") is Strategy.BALANCED

    def test_case_and_whitespace_insensitive(self):
        assert Strategy.parse("  AGGRESSIVE ") is Strategy.AGGRESSIVE

    def test_unknown_strategy_names_the_valid_ones(self):
        with pytest.raises(ValueError, match="conservative, balanced, aggressive"):
            Strategy.parse("nuclear")


class TestProtectedSpans:
    """Regression: the old optimizer rewrote code, URLs and placeholders."""

    def test_fenced_code_survives_verbatim(self):
        prompt = (
            "Please refactor this.\n\n"
            "```python\n"
            "def please_wait(very_long_timeout=30):\n"
            "    return kindly_retry()\n"
            "```\n"
        )
        result = optimizer.optimize(prompt, Strategy.AGGRESSIVE)

        assert "def please_wait(very_long_timeout=30):" in result.optimized
        assert "return kindly_retry()" in result.optimized

    def test_inline_code_survives(self):
        result = optimizer.optimize("Please call `really_do_it()` now.", Strategy.AGGRESSIVE)
        assert "`really_do_it()`" in result.optimized

    def test_urls_survive(self):
        url = "https://example.com/very/really/basically/path?x=please"
        result = optimizer.optimize(f"Please read {url} carefully.", Strategy.AGGRESSIVE)
        assert url in result.optimized

    @pytest.mark.parametrize(
        "placeholder",
        ["{{user_name}}", "{user_name}", "${user_name}", "%(user_name)s", "<USER_NAME>"],
    )
    def test_placeholders_survive(self, placeholder):
        result = optimizer.optimize(
            f"Please greet {placeholder} very warmly.", Strategy.AGGRESSIVE
        )
        assert placeholder in result.optimized

    def test_email_addresses_survive(self):
        result = optimizer.optimize("Please email really.important@example.com", Strategy.AGGRESSIVE)
        assert "really.important@example.com" in result.optimized


class TestStructurePreservation:
    """Regression: the old optimizer collapsed everything with \\s+ -> ' '."""

    def test_line_breaks_are_preserved(self):
        prompt = "Please do this:\n- item one\n- item two\n- item three"
        result = optimizer.optimize(prompt, Strategy.BALANCED)
        assert result.optimized.count("\n") == 3

    def test_paragraph_breaks_are_preserved(self):
        prompt = "Please summarize.\n\nThen please translate it."
        result = optimizer.optimize(prompt, Strategy.AGGRESSIVE)
        assert "\n\n" in result.optimized

    def test_excess_blank_lines_are_collapsed(self):
        result = optimizer.optimize("First.\n\n\n\n\nSecond.", Strategy.CONSERVATIVE)
        assert "\n\n\n" not in result.optimized

    def test_no_orphaned_punctuation_left_behind(self):
        result = optimizer.optimize("Summarize the notes.\nThanks in advance!", Strategy.BALANCED)
        assert not result.optimized.rstrip().endswith("!")
        assert "\n!" not in result.optimized


class TestTransformations:
    def test_conservative_removes_only_politeness(self):
        result = optimizer.optimize(
            "Please write a very detailed summary.", Strategy.CONSERVATIVE
        )
        assert "please" not in result.optimized.lower()
        assert "very" in result.optimized.lower(), "conservative must not touch intensifiers"

    def test_balanced_removes_intensifiers(self):
        result = optimizer.optimize("Write a very detailed summary.", Strategy.BALANCED)
        assert "very" not in result.optimized.lower()

    def test_verbose_phrases_are_shortened(self):
        result = optimizer.optimize(
            "In order to finish, due to the fact that it is late, act now.", Strategy.BALANCED
        )
        lowered = result.optimized.lower()
        assert "in order to" not in lowered
        assert "due to the fact that" not in lowered
        assert "because" in lowered

    def test_hedges_match_before_politeness_strips_their_filler(self):
        """"Could you please X" must collapse to "X", not "Could you X"."""
        result = optimizer.optimize("Could you please summarize the notes.", Strategy.BALANCED)
        assert not result.optimized.lower().startswith("could you")

    def test_aggressive_drops_duplicate_sentences(self):
        prompt = "Summarize the notes. Summarize the notes! Then stop."
        result = optimizer.optimize(prompt, Strategy.AGGRESSIVE)
        assert result.optimized.lower().count("summarize the notes") == 1

    def test_sentence_openings_are_recapitalized(self):
        result = optimizer.optimize("Please write the summary.", Strategy.CONSERVATIVE)
        assert result.optimized[0].isupper()

    def test_transformations_are_reported(self):
        result = optimizer.optimize("Please kindly write it.", Strategy.BALANCED)
        names = {t.name for t in result.transformations}
        assert "politeness" in names
        assert all(t.count >= 1 for t in result.transformations)


class TestRetentionScore:
    """Regression: quality_score was hardcoded to 0.95."""

    def test_score_is_measured_not_constant(self):
        untouched = optimizer.optimize("Analyze quarterly revenue data.", Strategy.BALANCED)
        stripped = optimizer.optimize(
            "Please could you very kindly analyze quarterly revenue data.", Strategy.AGGRESSIVE
        )
        assert untouched.retention_score == 1.0
        assert stripped.retention_score != 0.95 or untouched.retention_score != 0.95

    def test_removing_only_filler_keeps_a_perfect_score(self):
        result = optimizer.optimize(
            "Please kindly analyze the quarterly revenue data.", Strategy.BALANCED
        )
        assert result.retention_score == 1.0

    def test_numbers_are_never_dropped_silently(self):
        prompt = "Summarize the 3 action items and the 42 open tickets."
        result = optimizer.optimize(prompt, Strategy.AGGRESSIVE)
        assert "3" in result.optimized
        assert "42" in result.optimized
        assert not any("Numbers were lost" in w for w in result.warnings)

    def test_score_is_bounded(self):
        for strategy in Strategy:
            result = optimizer.optimize("Please very kindly do the thing.", strategy)
            assert 0.0 <= result.retention_score <= 1.0


class TestTokenAccounting:
    def test_optimization_never_increases_tokens(self):
        prompts = [
            "Hi.",
            "Please.",
            "In order to",
            "a",
            "Summarize this document in exactly three bullet points.",
            "Please please please please please",
        ]
        for prompt in prompts:
            for strategy in Strategy:
                result = optimizer.optimize(prompt, strategy)
                assert result.tokens_after <= result.tokens_before, (prompt, strategy)
                assert result.tokens_saved >= 0

    def test_reduction_ratio_matches_token_counts(self):
        result = optimizer.optimize(
            "Please kindly write a very detailed summary of everything.", Strategy.BALANCED
        )
        expected = result.tokens_saved / result.tokens_before
        assert result.reduction_ratio == pytest.approx(expected)

    @pytest.mark.parametrize("prompt", ["", "   ", "\n\n"])
    def test_empty_input_is_a_no_op(self, prompt):
        result = optimizer.optimize(prompt)
        assert result.optimized == prompt
        assert result.tokens_saved == 0
        assert result.retention_score == 1.0


class TestSerialization:
    def test_to_dict_round_trips_the_public_shape(self):
        payload = optimizer.optimize("Please summarize.", Strategy.BALANCED).to_dict()
        assert set(payload) >= {
            "original",
            "optimized",
            "strategy",
            "tokens_before",
            "tokens_after",
            "tokens_saved",
            "reduction_ratio",
            "retention_score",
            "transformations",
            "warnings",
        }
        assert payload["strategy"] == "balanced"

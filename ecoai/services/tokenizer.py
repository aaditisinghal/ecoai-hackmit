"""Token counting.

Exact counts require the target model's own tokenizer. Shipping one would mean
either a large vendored vocabulary or a network fetch on first use, and the
count is only ever used to compare a prompt against itself before and after
optimization - a ratio, where a systematic bias largely cancels out.

So this module implements a structural estimator instead: it reproduces the
pretokenization step that byte-pair encoders perform (split on whitespace and
punctuation, keep the leading space attached to a word) and then estimates
subword count per chunk. That is substantially closer than the ``len(text)/4``
rule the previous implementation used, which counted a 40-character URL as ten
tokens and a run of 40 spaces as ten as well.

If you need exact numbers, install ``tiktoken`` and inject its encoder:

    import tiktoken
    from ecoai.services import tokenizer
    enc = tiktoken.get_encoding("cl100k_base")
    tokenizer.set_token_counter(lambda text: len(enc.encode(text)))
"""

from __future__ import annotations

import math
import re
from collections.abc import Callable

# Mirrors the GPT-2/cl100k pretokenizer: contractions, then optional-leading-space
# runs of letters, digits, or symbols, then whitespace runs.
_PRETOKEN = re.compile(
    r"""'(?:[sdmt]|ll|ve|re)|"""  # contractions
    r""" ?[^\W\d_]+|"""           # words, optionally preceded by one space
    r""" ?\d+|"""                 # digit runs
    r""" ?[^\s\w]+|"""            # punctuation and symbol runs
    r"""\s+""",                   # whitespace
    re.UNICODE,
)

# CJK, Hangul and Kana are not alphabetic in the Latin sense; encoders spend
# roughly one token per character on them rather than merging into words.
_WIDE_SCRIPT = re.compile(r"[぀-ヿ㐀-䶿一-鿿가-힯]")

# Average characters per subword inside a single alphabetic run. Short words are
# one token; longer words fragment at roughly this rate.
_CHARS_PER_SUBWORD = 3.6
_SINGLE_TOKEN_WORD_LENGTH = 5
# Whitespace merges far more aggressively than text does.
_CHARS_PER_WHITESPACE_TOKEN = 8

_counter: Callable[[str], int] | None = None


def set_token_counter(counter: Callable[[str], int] | None) -> None:
    """Install an exact tokenizer, or pass None to restore the estimator."""
    global _counter
    _counter = counter


def count_tokens(text: str) -> int:
    """Return the token count for ``text``.

    Uses the injected tokenizer when one is configured, otherwise the built-in
    estimator. Always returns 0 for empty input and at least 1 otherwise, since
    no non-empty string encodes to zero tokens.
    """
    if not text:
        return 0
    if _counter is not None:
        return _counter(text)
    return max(1, _estimate(text))


def _estimate(text: str) -> int:
    total = 0
    for chunk in _PRETOKEN.findall(text):
        total += _estimate_chunk(chunk)
    return total


def _estimate_chunk(chunk: str) -> int:
    if not chunk:
        return 0

    stripped = chunk.strip()

    # Whitespace: a single space merges into the following word and costs
    # nothing extra. Longer runs are their own tokens, but they merge heavily -
    # cl100k carries dedicated tokens for runs of up to roughly sixteen spaces,
    # so indentation and blank lines are far cheaper than a per-character rule
    # would suggest.
    if not stripped:
        return 0 if len(chunk) == 1 else math.ceil(len(chunk) / _CHARS_PER_WHITESPACE_TOKEN)

    wide = len(_WIDE_SCRIPT.findall(stripped))
    if wide:
        # Roughly one token per wide character, plus the remainder as usual.
        remainder = len(stripped) - wide
        return wide + (math.ceil(remainder / _CHARS_PER_SUBWORD) if remainder else 0)

    if stripped.isdigit():
        # Encoders split long numbers into groups of up to three digits.
        return math.ceil(len(stripped) / 3)

    if stripped.isalpha():
        if len(stripped) <= _SINGLE_TOKEN_WORD_LENGTH:
            return 1
        return math.ceil(len(stripped) / _CHARS_PER_SUBWORD)

    # Punctuation and mixed alphanumeric runs fragment heavily; most symbols
    # stand alone and rarely merge with their neighbours.
    return len(stripped) if len(stripped) <= 3 else math.ceil(len(stripped) / 2)

"""Prompt optimization.

Reduces the token cost of a prompt without changing what it asks for.

The previous implementation ran ``re.sub`` for a handful of filler words over
the raw string and then flattened all whitespace with ``\\s+ -> ' '``. That had
three failure modes this module is built to avoid:

* it rewrote the inside of fenced code blocks, so ``please_wait()`` became
  ``_wait()``;
* it collapsed multi-line prompts - lists, examples, few-shot blocks - onto a
  single line, destroying structure the model depends on;
* it reported a hardcoded ``quality_score`` of 0.95 regardless of what it did.

Here, spans that must survive verbatim (code, URLs, template placeholders) are
extracted before any rewriting and restored afterwards, whitespace handling
preserves line structure, and the returned ``retention_score`` is measured
rather than asserted.

The score is lexical, not semantic: it is the fraction of *content* tokens -
words that are not stopwords, plus every number and protected span - that
survive optimization. 1.0 means nothing of substance was dropped. It is not an
embedding similarity, and it does not claim to be one.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from enum import Enum

from ecoai.services.tokenizer import count_tokens


class Strategy(str, Enum):
    """How aggressively to rewrite."""

    CONSERVATIVE = "conservative"
    BALANCED = "balanced"
    AGGRESSIVE = "aggressive"

    @classmethod
    def parse(cls, value: str | None) -> Strategy:
        if not value:
            return cls.BALANCED
        try:
            return cls(value.strip().lower())
        except ValueError as exc:
            valid = ", ".join(s.value for s in cls)
            raise ValueError(f"Unknown strategy {value!r}. Expected one of: {valid}.") from exc


# --- Protected spans --------------------------------------------------------
# Order matters: fenced blocks are matched before inline code so a ``` block
# containing backticks is captured whole.
_PROTECTED_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("fenced_code", re.compile(r"```.*?```", re.DOTALL)),
    ("indented_code", re.compile(r"(?:^|\n)(?: {4}|\t)[^\n]*(?:\n(?: {4}|\t)[^\n]*)*")),
    ("inline_code", re.compile(r"`[^`\n]+`")),
    ("url", re.compile(r"https?://\S+|www\.\S+")),
    ("email", re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.]+\b")),
    # Template placeholders in every common dialect: {{x}}, {x}, ${x}, <x>, %(x)s
    ("placeholder", re.compile(r"\{\{.*?\}\}|\$\{.*?\}|\{[A-Za-z_]\w*\}|%\(\w+\)[sdf]")),
    ("angle_placeholder", re.compile(r"<[A-Z][A-Z0-9_]{2,}>")),
)

_SENTINEL = "\x00P{}\x00"
_SENTINEL_RE = re.compile(r"\x00P(\d+)\x00")


# --- Vocabulary -------------------------------------------------------------

_POLITENESS = (
    r"please",
    r"kindly",
    r"thanks in advance",
    r"thank you in advance",
    r"much appreciated",
    r"i'd appreciate it",
    r"i would appreciate it",
    r"if you don't mind",
    r"if you would be so kind",
)

_HEDGES = (
    r"i was wondering if you could",
    r"i was hoping you could",
    r"could you please",
    r"can you please",
    r"would you please",
    r"could you kindly",
    r"i would like you to",
    r"i'd like you to",
    r"i want you to",
    r"i need you to",
    r"it would be great if you could",
    r"do you think you could",
)

_INTENSIFIERS = (
    r"very",
    r"really",
    r"quite",
    r"extremely",
    r"incredibly",
    r"highly",
    r"super",
    r"actually",
    r"basically",
    r"essentially",
    r"literally",
    r"definitely",
    r"certainly",
    r"absolutely",
)

# Verbose construction -> concise equivalent. Meaning-preserving substitutions
# only; anything that would change scope or modality is excluded.
_VERBOSE_PHRASES: tuple[tuple[str, str], ...] = (
    (r"in order to", "to"),
    (r"due to the fact that", "because"),
    (r"owing to the fact that", "because"),
    (r"in spite of the fact that", "although"),
    (r"despite the fact that", "although"),
    (r"in the event that", "if"),
    (r"at this point in time", "now"),
    (r"at the present time", "now"),
    (r"in the near future", "soon"),
    (r"a large number of", "many"),
    (r"a small number of", "a few"),
    (r"the majority of", "most"),
    (r"has the ability to", "can"),
    (r"have the ability to", "can"),
    (r"is able to", "can"),
    (r"are able to", "can"),
    (r"for the purpose of", "for"),
    (r"with regard to", "about"),
    (r"with respect to", "about"),
    (r"in relation to", "about"),
    (r"prior to", "before"),
    (r"subsequent to", "after"),
    (r"in the process of", "currently"),
    (r"it is important to note that", ""),
    (r"it should be noted that", ""),
    (r"make sure to", ""),
    (r"be sure to", ""),
)

_META_INSTRUCTIONS = (
    r"as an ai(?: language model)?,?",
    r"you are an ai(?: language model)?,?",
    r"remember that you",
    r"i know you can do this",
    r"take your time",
    r"think step by step about how to",
)

# Words carrying no topical content. Filler removed by the transforms above is
# deliberately included, so removing it cannot depress the retention score.
_STOPWORDS = frozenset(
    """
    a an the and or but if then else when while of to in on at by for with from into
    over under again further once here there all any both each few more most other some
    such only own same so than too can will just should now i me my we our you your he
    him his she her it its they them their this that these those am is are was were be
    been being have has had having do does did doing would could shall may might must
    about as up down out off above below between through during before after
    please kindly thanks thank appreciate mind
    very really quite extremely incredibly highly super actually basically essentially
    literally definitely certainly absolutely
    """.split()
)

_WORD_RE = re.compile(r"[A-Za-z0-9_]+(?:'[A-Za-z]+)?")
_NUMBER_RE = re.compile(r"\d+(?:\.\d+)?")
# Capturing group so the whitespace between sentences can be restored verbatim.
_SENTENCE_SPLIT = re.compile(r"((?<=[.!?])\s+)")
# A line left holding nothing but punctuation, e.g. the "!" stranded by
# removing "Thanks in advance!". Sentinels count as content and are excluded.
_ORPHAN_LINE = re.compile(r"^[^\w\x00]*$")


@dataclass
class Transformation:
    """A rewrite rule that fired, and how often."""

    name: str
    count: int
    detail: str = ""

    def to_dict(self) -> dict:
        return {"name": self.name, "count": self.count, "detail": self.detail}


@dataclass
class OptimizationResult:
    """Outcome of optimizing a single prompt."""

    original: str
    optimized: str
    strategy: Strategy
    tokens_before: int
    tokens_after: int
    retention_score: float
    transformations: list[Transformation] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def tokens_saved(self) -> int:
        return self.tokens_before - self.tokens_after

    @property
    def reduction_ratio(self) -> float:
        return self.tokens_saved / self.tokens_before if self.tokens_before else 0.0

    def to_dict(self) -> dict:
        return {
            "original": self.original,
            "optimized": self.optimized,
            "strategy": self.strategy.value,
            "tokens_before": self.tokens_before,
            "tokens_after": self.tokens_after,
            "tokens_saved": self.tokens_saved,
            "reduction_ratio": self.reduction_ratio,
            "retention_score": self.retention_score,
            "transformations": [t.to_dict() for t in self.transformations],
            "warnings": list(self.warnings),
        }


class PromptOptimizer:
    """Rewrites prompts to cost fewer tokens while preserving their content."""

    #: Below this retention score the result carries a warning.
    RETENTION_WARNING_THRESHOLD = 0.85

    def optimize(self, prompt: str, strategy: Strategy | str = Strategy.BALANCED) -> OptimizationResult:
        strategy = strategy if isinstance(strategy, Strategy) else Strategy.parse(strategy)

        if not prompt or not prompt.strip():
            return OptimizationResult(
                original=prompt,
                optimized=prompt,
                strategy=strategy,
                tokens_before=0,
                tokens_after=0,
                retention_score=1.0,
            )

        tokens_before = count_tokens(prompt)

        masked, protected = self._mask_protected(prompt)
        transformations: list[Transformation] = []

        # Hedges run first: they are multi-word phrases that contain the same
        # filler the politeness pass strips. Removing "please" first would
        # leave "Could you write ..." and the longer phrase would never match.
        if strategy in (Strategy.BALANCED, Strategy.AGGRESSIVE):
            masked = self._apply_hedges(masked, transformations)

        masked = self._apply_politeness(masked, transformations)

        if strategy in (Strategy.BALANCED, Strategy.AGGRESSIVE):
            masked = self._apply_intensifiers(masked, transformations)
            masked = self._apply_verbose_phrases(masked, transformations)

        if strategy is Strategy.AGGRESSIVE:
            masked = self._apply_meta_instructions(masked, transformations)
            masked = self._remove_duplicate_sentences(masked, transformations)

        masked = self._tidy(masked, transformations)
        optimized = self._unmask(masked, protected)

        tokens_after = count_tokens(optimized)
        retention, warnings = self._score_retention(prompt, optimized, protected)

        # Never hand back something longer than we were given.
        if tokens_after > tokens_before:
            return OptimizationResult(
                original=prompt,
                optimized=prompt,
                strategy=strategy,
                tokens_before=tokens_before,
                tokens_after=tokens_before,
                retention_score=1.0,
                transformations=[],
                warnings=["Optimization would have increased token count; original kept."],
            )

        return OptimizationResult(
            original=prompt,
            optimized=optimized,
            strategy=strategy,
            tokens_before=tokens_before,
            tokens_after=tokens_after,
            retention_score=retention,
            transformations=transformations,
            warnings=warnings,
        )

    # -- Masking -----------------------------------------------------------

    def _mask_protected(self, text: str) -> tuple[str, list[str]]:
        """Swap spans that must survive verbatim for opaque sentinels."""
        protected: list[str] = []

        for _name, pattern in _PROTECTED_PATTERNS:
            def replace(match: re.Match[str]) -> str:
                protected.append(match.group(0))
                return _SENTINEL.format(len(protected) - 1)

            text = pattern.sub(replace, text)

        return text, protected

    def _unmask(self, text: str, protected: list[str]) -> str:
        def restore(match: re.Match[str]) -> str:
            index = int(match.group(1))
            return protected[index] if index < len(protected) else match.group(0)

        return _SENTINEL_RE.sub(restore, text)

    # -- Transformations ---------------------------------------------------

    def _apply_politeness(self, text: str, log: list[Transformation]) -> str:
        return self._remove_terms(text, _POLITENESS, "politeness", log)

    def _apply_hedges(self, text: str, log: list[Transformation]) -> str:
        return self._remove_terms(text, _HEDGES, "hedging", log)

    def _apply_intensifiers(self, text: str, log: list[Transformation]) -> str:
        return self._remove_terms(text, _INTENSIFIERS, "intensifiers", log)

    def _apply_meta_instructions(self, text: str, log: list[Transformation]) -> str:
        return self._remove_terms(text, _META_INSTRUCTIONS, "meta-instructions", log)

    def _remove_terms(
        self, text: str, terms: tuple[str, ...], label: str, log: list[Transformation]
    ) -> str:
        removed: list[str] = []
        for term in terms:
            pattern = re.compile(rf"\b{term}\b[ \t]*", re.IGNORECASE)
            text, hits = pattern.subn("", text)
            if hits:
                removed.extend([term.replace("\\", "")] * hits)
        if removed:
            unique = sorted(set(removed))
            log.append(
                Transformation(
                    name=label,
                    count=len(removed),
                    detail=", ".join(unique[:6]) + ("..." if len(unique) > 6 else ""),
                )
            )
        return text

    def _apply_verbose_phrases(self, text: str, log: list[Transformation]) -> str:
        replaced = 0
        examples: list[str] = []
        for verbose, concise in _VERBOSE_PHRASES:
            pattern = re.compile(rf"\b{verbose}\b", re.IGNORECASE)

            def substitute(match: re.Match[str], concise=concise) -> str:
                if not concise:
                    return ""
                # Keep the original capitalization of the first character.
                return concise.capitalize() if match.group(0)[:1].isupper() else concise

            text, hits = pattern.subn(substitute, text)
            if hits:
                replaced += hits
                examples.append(f"{verbose} -> {concise or '(removed)'}")

        if replaced:
            log.append(
                Transformation(
                    name="verbose-phrases",
                    count=replaced,
                    detail="; ".join(examples[:4]) + ("..." if len(examples) > 4 else ""),
                )
            )
        return text

    def _remove_duplicate_sentences(self, text: str, log: list[Transformation]) -> str:
        """Drop later repetitions of a sentence already present.

        Comparison is on normalized content words, so "Summarize the notes."
        and "Summarize the notes!" count as the same sentence.

        The separators between sentences are captured and reused rather than
        replaced with a space, so paragraph breaks, list layout and the blank
        lines around fenced blocks all survive.
        """
        parts = _SENTENCE_SPLIT.split(text)
        if len(parts) < 3:
            return text

        seen: set[str] = set()
        kept: list[str] = []
        dropped = 0

        # Alternates sentence, separator, sentence, separator, ...
        for index in range(0, len(parts), 2):
            sentence = parts[index]
            separator = parts[index + 1] if index + 1 < len(parts) else ""

            fingerprint = " ".join(sorted(_content_words(sentence)))
            if fingerprint and fingerprint in seen:
                dropped += 1
                continue
            if fingerprint:
                seen.add(fingerprint)
            kept.append(sentence + separator)

        if dropped:
            log.append(Transformation(name="duplicate-sentences", count=dropped))
        return "".join(kept)

    def _tidy(self, text: str, log: list[Transformation]) -> str:
        """Repair the whitespace and punctuation artefacts removals leave behind.

        Line structure is preserved throughout - lists, examples and few-shot
        blocks depend on it.
        """
        before = text

        # Space runs within a line, but never across newlines.
        text = re.sub(r"[ \t]{2,}", " ", text)
        # Space stranded before punctuation by a removal.
        text = re.sub(r"[ \t]+([,.;:!?])", r"\1", text)
        # Leftover double punctuation, e.g. "summary,." from a dropped clause.
        text = re.sub(r",\s*([.;:!?])", r"\1", text)
        # Trailing whitespace per line.
        text = re.sub(r"[ \t]+$", "", text, flags=re.MULTILINE)

        # Lines reduced to bare punctuation by a removal are dropped entirely.
        text = "\n".join(
            line for line in text.split("\n") if not (line.strip() and _ORPHAN_LINE.match(line.strip()))
        )
        # Same artefact mid-line: " . " or a stray "!" left between words.
        text = re.sub(r"(?<=\w)\s+([.!?,;:])(?=\s|$)", r"\1", text)

        # Three or more blank lines collapse to one.
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = text.strip()

        # Re-capitalize sentence openings a removal left lowercase
        # ("Please write X" -> "write X" -> "Write X").
        def capitalize(match: re.Match[str]) -> str:
            return match.group(1) + match.group(2).upper()

        text = re.sub(r"(^|[.!?]\s+|\n)([a-z])", capitalize, text)

        if text != before:
            log.append(Transformation(name="whitespace-and-punctuation", count=1))
        return text

    # -- Scoring -----------------------------------------------------------

    def _score_retention(
        self, original: str, optimized: str, protected: list[str]
    ) -> tuple[float, list[str]]:
        """Fraction of content preserved, plus any warnings raised."""
        warnings: list[str] = []

        before = Counter(_content_words(original))
        after = Counter(_content_words(optimized))

        if not before:
            score = 1.0
        else:
            retained = sum((before & after).values())
            score = retained / sum(before.values())

        # Numbers are never safe to drop - a changed quantity changes the task.
        numbers_before = Counter(_NUMBER_RE.findall(original))
        numbers_after = Counter(_NUMBER_RE.findall(optimized))
        missing_numbers = numbers_before - numbers_after
        if missing_numbers:
            warnings.append(
                "Numbers were lost during optimization: "
                + ", ".join(sorted(missing_numbers.elements()))
            )
            score = min(score, 0.5)

        # Every protected span must reappear verbatim.
        missing_spans = [span for span in protected if span not in optimized]
        if missing_spans:
            warnings.append(
                f"{len(missing_spans)} protected span(s) - code, URLs or placeholders - "
                "did not survive and the original should be used instead."
            )
            score = min(score, 0.3)

        if score < self.RETENTION_WARNING_THRESHOLD and not warnings:
            # Three decimals: at two, a score of 0.846 rounds to 0.85 and the
            # message reads "0.85 is below 0.85".
            warnings.append(
                f"Retention score {score:.3f} is below the "
                f"{self.RETENTION_WARNING_THRESHOLD:.2f} threshold; review before using."
            )

        return round(score, 4), warnings


def _content_words(text: str) -> list[str]:
    """Topical words: lowercase, stopwords removed, sentinels ignored."""
    cleaned = _SENTINEL_RE.sub(" ", text)
    return [
        word
        for word in (match.group(0).lower() for match in _WORD_RE.finditer(cleaned))
        if word not in _STOPWORDS and len(word) > 1
    ]


#: Shared stateless instance.
optimizer = PromptOptimizer()

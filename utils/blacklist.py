"""
Blacklist word filter with support for exact matches,
partial matches, and basic leet-speak normalization.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

# ── Leet-speak character substitutions ───────────────────────────────────────
_LEET_MAP: dict[str, str] = {
    "0": "o",
    "1": "i",
    "3": "e",
    "4": "a",
    "5": "s",
    "7": "t",
    "@": "a",
    "$": "s",
    "!": "i",
    "+": "t",
}

# ── Default blacklisted words (extend via blacklist.txt) ─────────────────────
_DEFAULT_BLACKLIST: set[str] = {
    # Add base words here — kept minimal; load from file for real use
}

_BLACKLIST_FILE = Path(__file__).resolve().parent.parent / "blacklist.txt"


class BlacklistFilter:
    """Fast blacklist word detector with leet-speak normalization."""

    def __init__(self) -> None:
        self._words: set[str] = set(_DEFAULT_BLACKLIST)
        self._pattern: re.Pattern | None = None
        self._load_from_file()
        self._compile_pattern()

    # ── Public API ───────────────────────────────────────────────────────

    def check(self, text: str) -> tuple[bool, list[str]]:
        """
        Check *text* for blacklisted words.

        Returns:
            (is_flagged, list_of_matched_words)
        """
        if not self._words:
            return False, []

        normalized = self._normalize(text)
        matches: list[str] = []

        if self._pattern and self._pattern.search(normalized):
            for word in self._words:
                if word in normalized:
                    matches.append(word)

        return bool(matches), matches

    def add_word(self, word: str) -> None:
        """Add a word to the blacklist at runtime."""
        self._words.add(word.lower().strip())
        self._compile_pattern()

    def remove_word(self, word: str) -> None:
        """Remove a word from the blacklist at runtime."""
        self._words.discard(word.lower().strip())
        self._compile_pattern()

    @property
    def word_count(self) -> int:
        return len(self._words)

    # ── Internal ─────────────────────────────────────────────────────────

    def _load_from_file(self) -> None:
        """Load words from blacklist.txt (one word per line)."""
        if not _BLACKLIST_FILE.exists():
            logger.info(
                "No blacklist.txt found at %s — using defaults only.", _BLACKLIST_FILE
            )
            return
        with open(_BLACKLIST_FILE, encoding="utf-8") as f:
            for line in f:
                word = line.strip().lower()
                if word and not word.startswith("#"):
                    self._words.add(word)
        logger.info("Loaded %d blacklisted words from file.", len(self._words))

    def _compile_pattern(self) -> None:
        """Compile a combined regex for fast first-pass matching."""
        if not self._words:
            self._pattern = None
            return
        escaped = [re.escape(w) for w in sorted(self._words, key=len, reverse=True)]
        self._pattern = re.compile("|".join(escaped), re.IGNORECASE)

    @staticmethod
    def _normalize(text: str) -> str:
        """Normalize text: lowercase + leet-speak substitution."""
        text = text.lower()
        result: list[str] = []
        for ch in text:
            result.append(_LEET_MAP.get(ch, ch))
        # Strip non-alpha between letters to catch "f u c k" → "fuck"
        collapsed = re.sub(r"[^a-z]", "", "".join(result))
        # Also keep original with spaces collapsed for phrase matching
        spaced = re.sub(r"\s+", " ", "".join(result))
        return f"{collapsed} {spaced}"


# ── Module-level singleton ───────────────────────────────────────────────────
blacklist_filter = BlacklistFilter()

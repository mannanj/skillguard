r"""skillguard/sanitize.py — the single text-safety authority.

SkillGuard reads untrusted skill source and then (a) matches detection patterns
against it and (b) echoes excerpts of it back — to a terminal, to a JSON/markdown
report, to the SQLite/JSON cache, and to the PreToolUse hook's stdout, which an
agent harness in turn reads. Raw skill bytes on either path are an attack
surface:

  * Detection evasion — a single zero-width char (a U+200B inside "curl"), a
    bidirectional override (Trojan Source, CVE-2021-42574), or an NFKC look-alike
    lets a payload slip past a regex that matches only the visible form.
  * Output spoofing — an ANSI/terminal escape or C0/C1 control char embedded in
    skill text can move the cursor, erase a line, or recolor output, letting a
    skill hide a finding or fake a clean result when SkillGuard prints its
    excerpt; the same bytes, fed to the agent harness that reads the hook output,
    are an injection vector.

This module is the ONE place that defangs both, mirroring how ``mcp/secrets.py``
is the single redaction authority. Two entry points:

  * :func:`fold_for_detection` — collapse invisible/bidi obfuscation (and NFKC
    look-alikes) so the regex engine sees the canonical form. Returns the input
    UNCHANGED when it holds no invisible/bidi char, so benign emoji, accents,
    CJK, and full-width text are never NFKC-folded into a spurious match.
  * :func:`sanitize_for_display` — strip ANSI escapes and C0/C1 control chars and
    render invisible/bidi code points as visible ``<U+XXXX>`` tokens, so the text
    is safe to print and carries no hidden directives.

``hook.py`` runs standalone (it import-guards the package), so it mirrors
:func:`sanitize_for_display` as an inline ``_sanitize``; the two are pinned
together by ``tests/test_hook.py::test_sanitize_mirrors_package``. Keep this
implementation simple enough to mirror exactly.

The special code points are defined by integer value, not as literal characters:
a module that defangs invisible characters must not itself contain unreviewable
invisible characters in its source.

Homoglyph / mixed-script (confusables, TR39 skeleton) detection is deliberately
out of scope here — it is a separate, heavier piece tracked in
``task-scanner-self-resilience.md`` and ``task-skills-registry-threat-models.md``.
A full-width-only payload with no invisible/bidi char is therefore not folded; a
benign full-width heading is left untouched (the documented FP trade-off).
"""

from __future__ import annotations

import re
import unicodedata

# Zero-width / invisible format code points. U+200D (ZERO WIDTH JOINER) also
# appears in legitimate emoji sequences, so detection RULES only flag these in
# ASCII-adjacent (evasion) context (see patterns.py); folding and display strip
# or surface them all regardless.
_INVISIBLE_CODEPOINTS = (
    0x200B,  # ZERO WIDTH SPACE
    0x200C,  # ZERO WIDTH NON-JOINER
    0x200D,  # ZERO WIDTH JOINER
    0x2060,  # WORD JOINER
    0xFEFF,  # ZERO WIDTH NO-BREAK SPACE / BOM
    0x00AD,  # SOFT HYPHEN
    0x180E,  # MONGOLIAN VOWEL SEPARATOR
)

# Bidirectional formatting controls (Trojan Source, CVE-2021-42574): embeddings,
# overrides, and isolates that reorder displayed text relative to logical byte
# order, plus the LRM/RLM marks.
_BIDI_CODEPOINTS = (
    0x202A,  # LEFT-TO-RIGHT EMBEDDING
    0x202B,  # RIGHT-TO-LEFT EMBEDDING
    0x202C,  # POP DIRECTIONAL FORMATTING
    0x202D,  # LEFT-TO-RIGHT OVERRIDE
    0x202E,  # RIGHT-TO-LEFT OVERRIDE
    0x2066,  # LEFT-TO-RIGHT ISOLATE
    0x2067,  # RIGHT-TO-LEFT ISOLATE
    0x2068,  # FIRST STRONG ISOLATE
    0x2069,  # POP DIRECTIONAL ISOLATE
    0x200E,  # LEFT-TO-RIGHT MARK
    0x200F,  # RIGHT-TO-LEFT MARK
)

INVISIBLE_CHARS = frozenset(chr(cp) for cp in _INVISIBLE_CODEPOINTS)
BIDI_CHARS = frozenset(chr(cp) for cp in _BIDI_CODEPOINTS)

# Single source of truth for "characters that are invisible or reorder text".
STRIP_CHARS = INVISIBLE_CHARS | BIDI_CHARS

# ANSI / terminal escape sequences: CSI (ESC ``[`` ... final byte), OSC
# (ESC ``]`` ... BEL or ST), and two-char Fe escapes (ESC <0x40-0x5f>). A lone
# ESC and every other C0/C1 control byte are removed by the control-char pass.
_ANSI_RE = re.compile(
    r"\x1b\[[0-?]*[ -/]*[@-~]"  # CSI
    r"|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)"  # OSC ... BEL or ST
    r"|\x1b[@-Z\\-_]"  # two-char Fe escape
)

# C0 (0x00-0x1f) and C1/DEL (0x7f-0x9f) control chars, excluding tab (0x09).
# Newline never appears here: callers sanitize single lines.
_CONTROL_RE = re.compile(r"[\x00-\x08\x0a-\x1f\x7f-\x9f]")


def fold_for_detection(text: str) -> str:
    """Return *text* with invisible/bidi chars removed and NFKC-normalized, so a
    detection regex sees through obfuscation (e.g. a U+200B inside "curl" folds
    back to ``curl``).

    Returns *text* unchanged when it contains no invisible/bidi character — the
    false-positive guard, so benign emoji / accents / CJK / full-width text is
    never NFKC-folded into a spurious match.
    """
    if not any(ch in STRIP_CHARS for ch in text):
        return text
    folded = "".join(ch for ch in text if ch not in STRIP_CHARS)
    return unicodedata.normalize("NFKC", folded)


def sanitize_for_display(text: str) -> str:
    """Make untrusted skill text safe to print or hand to an agent harness:
    strip ANSI escapes and C0/C1 control chars, and render invisible/bidi code
    points as visible ``<U+XXXX>`` tokens. Idempotent.
    """
    text = _ANSI_RE.sub("", text)
    text = _CONTROL_RE.sub("", text)
    return "".join(f"<U+{ord(ch):04X}>" if ch in STRIP_CHARS else ch for ch in text)

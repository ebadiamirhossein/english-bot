"""S1d layout helper and reaction coverage."""

from __future__ import annotations

from app import texts
from app.handlers.onboarding import layout_buttons


def _all_option_reaction_keys() -> set[str]:
    """Every choosable option key that must have a reaction string."""
    keys: set[str] = {
        "name:yes",
        "name:other",
        "name:typed",
        "lang:fa",
        "lang:lt",
        "lang:ru",
        "lang:pl",
        "lang:other",
        "lang:typed",
        "efset:know",
        "efset:skip",
        "efset_score:A1",
        "efset_score:A2",
        "efset_score:B1",
        "efset_score:B2",
        "efset_score:C1",
        "efset_score:C2",
        "domain:other",
        "domain:typed",
        "why:done",
        "weights:balanced",
        "weights:work",
        "weights:life",
        "morning:07:00",
        "morning:08:00",
        "morning:09:00",
        "morning:other",
        "morning:typed",
        "evening:19:00",
        "evening:20:00",
        "evening:21:00",
        "evening:other",
        "evening:typed",
    }
    for key, _label, _cefr in texts.SELF_ASSESS_OPTIONS:
        keys.add(f"level:{key}")
    for cat, _label in texts.DOMAIN_CATEGORIES:
        keys.add(f"domain:cat:{cat}")
    for cat, specifics in texts.DOMAIN_SPECIFICS.items():
        for spec_key, _label in specifics:
            keys.add(f"domain:pick:{spec_key}")
    for key, _label, _clause in texts.WHY_OPTIONS:
        keys.add(f"why:{key}")
    return keys


def test_layout_never_shares_row_when_label_over_12() -> None:
    items = [
        ("Short", "a"),
        ("Also short", "b"),
        ("This label is definitely too long for sharing", "c"),
        ("Ok", "d"),
        ("Fine", "e"),
    ]
    rows = layout_buttons(items)
    for row in rows:
        if len(row) > 1:
            for label, _cb in row:
                assert len(label) <= 12, label
    # Long label must be alone
    assert any(len(row) == 1 and "definitely too long" in row[0][0] for row in rows)


def test_layout_times_three_short_labels_share_a_row() -> None:
    items = [
        (texts.BTN_MORNING_07, "wiz:morning:07:00"),
        (texts.BTN_MORNING_08, "wiz:morning:08:00"),
        (texts.BTN_MORNING_09, "wiz:morning:09:00"),
    ]
    rows = layout_buttons(items, max_per_row=3)
    assert len(rows) == 1
    assert len(rows[0]) == 3
    for label, _cb in rows[0]:
        assert len(label) <= 12, (label, len(label))


def test_every_option_has_reaction_under_60_chars() -> None:
    required = _all_option_reaction_keys()
    missing = sorted(required - set(texts.REACTIONS))
    assert missing == [], f"Missing reactions for: {missing}"
    for key in required:
        reaction = texts.REACTIONS[key]
        assert reaction.strip(), key
        assert len(reaction) <= 60, f"{key} is {len(reaction)} chars: {reaction!r}"

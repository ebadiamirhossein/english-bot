"""`core.runs.band` — the instrument that reports a pre-registered prediction.

**It has printed a false reading twice, in the same way**, which is why W10b
promoted it to a shared module rather than copying it: #201 (it printed MET over
gates no item ever reached) and its sequel (it reverted to the old claim the
moment a single item arrived, so the fix held only at exactly n=0). Both
regressions are pinned here.
"""

from __future__ import annotations

from core.runs import band, confirm


def test_a_value_inside_the_band_is_met(capsys) -> None:
    assert band("P", 2, 0, 3, 24, "over") is True
    assert "MET" in capsys.readouterr().out


def test_a_value_outside_the_band_is_not_met_and_prints_the_branch_rule(capsys) -> None:
    assert band("P", 9, 0, 3, 24, "rewrite the prompt") is False
    out = capsys.readouterr().out
    assert "NOT MET" in out
    assert "rewrite the prompt" in out


def test_nothing_reached_the_gate_is_never_reported_as_met(capsys) -> None:
    """#201. `0 of 24 — MET` from a run where nothing was checked is a lie."""
    assert band("P", 0, 0, 3, 24, "over", exercised=0) is False
    out = capsys.readouterr().out
    assert "NOT EVALUATED" in out
    assert "never asked" in out
    assert "MET" not in out.replace("NOT EVALUATED", "")


def test_a_partial_denominator_is_not_comparable(capsys) -> None:
    """The sequel: the zero fix reverted to the old claim at n=1.

    A prediction registered over 24 cannot be evaluated when one item reached the
    gate -- `0 of 24 — MET` reads as *twenty-four were checked and none drifted*.
    """
    assert band("P", 0, 0, 3, 24, "over", exercised=1) is False
    out = capsys.readouterr().out
    assert "NOT COMPARABLE" in out
    assert "did not happen" in out


def test_a_full_denominator_says_so(capsys) -> None:
    assert band("P", 1, 0, 3, 24, "over", exercised=24) is True
    assert "all 24 evaluated" in capsys.readouterr().out


def test_confirm_accepts_only_the_exact_string(monkeypatch) -> None:
    monkeypatch.setattr("builtins.input", lambda _: " 174 ")
    assert confirm("", "174") is True
    monkeypatch.setattr("builtins.input", lambda _: "yes")
    assert confirm("", "174") is False


def test_confirm_prints_the_expected_value(monkeypatch, capsys) -> None:
    """**The value is COMPUTED and shown, never transcribed from a document.**

    An earlier draft of W10b's plan carried literal values in one section and
    staged ones in another -- two sources of truth for the string typed at the
    moment money is spent, which is #223's shape one field over and worse than no
    guard.
    """
    seen: list[str] = []
    monkeypatch.setattr("builtins.input", lambda prompt: seen.append(prompt) or "60")
    assert confirm("", "60") is True
    assert "60" in seen[0]


def test_the_items_generator_uses_the_promoted_functions_and_not_a_copy() -> None:
    """Promoted, not copied. A second copy is a second place for #201 to return."""
    from core.items import generate as items_generate

    assert items_generate._band is band
    assert items_generate._confirm is confirm

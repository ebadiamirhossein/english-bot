"""Reporting and confirmation for the human-run billed scripts.

**Two functions, promoted here rather than copied.** Both were private to
`core.items.generate` until W10b needed the identical behaviour for lessons, and
copying either would have been the wrong move for a reason this record has
already counted:

- `band` is the instrument that reports a pre-registered prediction, and it has
  been wrong twice in the same way -- #201 (it printed `MET` over gates no item
  ever reached) and its ninth-appearance sequel (it reverted to the old claim the
  moment a single item arrived, so the fix held only at exactly n=0). A second
  copy would be a second place for that family to reappear, in a slice whose
  whole subject is measuring things honestly.
- `confirm` is the guard on the moment money is spent. Two implementations of a
  typed confirmation is two places for the expected string to drift from what the
  operator was told to type, which is #223's shape one field over.

**Pure except for `print` and `input`.** No database, no model, no HTTP -- so
this module is covered by `test_core_imports_no_web_framework` and
`test_no_sql_outside_services` for free, and it is importable from any run
script without dragging a package's constants along with it.
"""

from __future__ import annotations


def band(
    name: str, value: int, low: int, high: int, total: int, over: str,
    *, exercised: int | None = None,
) -> bool:
    """One axis, evaluated — or reported as NOT EVALUATED when nothing reached it.

    **`exercised` exists because of a false reading this function produced on
    2026-08-27.** The second `--live` attempt rejected all 24 items at the
    GENERATION stage, so nothing reached the naturalness judge or the probe --
    and P2 and P3 printed **MET**, because zero drift and zero unnatural
    sentences both fall inside their predicted bands. **They were not met; they
    were never asked.**

    That is CLAUDE.md §3 rule 4 -- *a green test over an unreachable path proves
    nothing* -- appearing inside the instrument that reports the predictions.
    A record carrying "P2 MET" from a run where no item was ever target-checked
    would be false in the file that exists to be trusted.
    """
    if exercised is not None and exercised == 0:
        print(f"  {name}: NOT EVALUATED — no item reached this gate. "
              f"**Not met, not unmet: never asked.**")
        return False
    if exercised is not None and exercised < total:
        # **THE PARTIAL CASE, and #201 fixed only the zero case.**
        # A prediction registered as "0-3 of 24" cannot be evaluated when one
        # item reached the gate: `0 of 24 — MET` reads as *twenty-four items
        # were checked and none drifted*, when one was checked. The zero case
        # printed NOT EVALUATED and the code then **reverted to the old claim
        # the moment a single item arrived** -- so the fix held only at exactly
        # n=0, which is the one value where the bug is least misleading.
        print(f"  {name}: {value} of {exercised} EVALUATED "
              f"({total} drafted) — predicted {low}-{high} of {total} — "
              f"**NOT COMPARABLE**")
        print(f"      The prediction was registered over {total}. At "
              f"{exercised} evaluated it is neither met nor unmet:\n"
              f"      the denominator it names did not happen.")
        return False
    met = low <= value <= high
    shown = f"{value} of {total}"
    if exercised is not None:
        shown += f" (all {exercised} evaluated)"
    print(f"  {name}: {shown} — predicted {low}-{high} — "
          f"{'MET' if met else 'NOT MET'}")
    if not met:
        print(f"      {over}")
    return met


def confirm(prompt: str, expected: str) -> bool:
    """Type it back. There is no `--yes`, deliberately.

    The guard `seed_fixtures`, `rewrite_checkpoints` and `retire_chunk_cloze`
    all use, for the same reason: a flag that can be pasted out of a runbook is
    not a decision.

    **`expected` is always COMPUTED by the caller for the invocation actually
    running, never transcribed from a document** (W10b). An earlier draft of
    W10b's plan carried literal values in one section while another section
    carried the staged ones -- two sources of truth for the string typed at the
    moment money is spent, which is worse than no guard: the operator reads the
    document, types the value, is rejected, and reasonably concludes the guard is
    broken. The prompt below prints the expected value for that reason.
    """
    typed = input(f"{prompt} Type {expected} to continue, anything else to stop: ")
    return typed.strip() == expected

"""W16a: `WRITING_MAX_SUBMISSIONS_PER_DAY`, set the way it is really set.

CLAUDE.md §3 rule 3. In v2, eighteen tests passed a variable as a process
environment variable while the only real path — a `.env` file — was never read.
So these write a `.env` and name it, with the process variable dropped first:
process variables win over the file, and `load_dotenv()` would otherwise find
the repo-root `.env` whatever the caller (#64). The helper is
`tests/test_backup_r2.py::write_dotenv`, the precedent `tests/test_worker.py`
already uses.

**RED DEMONSTRATION:** the `writing_max_submissions_per_day` argument removed
from `Settings(...)` in `load_settings` turned `test_the_ceiling_is_read_from_the_env_file`
red; the `< 1` check removed turned `test_a_ceiling_below_one_is_refused` red.
"""

from __future__ import annotations

import pytest

from core import config as config_mod
from tests.test_backup_r2 import write_dotenv

KEY = "WRITING_MAX_SUBMISSIONS_PER_DAY"


def test_the_ceiling_defaults_to_five(tmp_path, monkeypatch) -> None:
    """Ruling 3's number, hardcoded (§3 rule 5)."""
    monkeypatch.delenv(KEY, raising=False)
    settings = config_mod.load_settings(dotenv_path=write_dotenv(tmp_path))
    assert settings.writing_max_submissions_per_day == 5


def test_the_ceiling_is_read_from_the_env_file(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv(KEY, raising=False)
    settings = config_mod.load_settings(dotenv_path=write_dotenv(tmp_path, **{KEY: "3"}))
    assert settings.writing_max_submissions_per_day == 3


@pytest.mark.parametrize("value", ["0", "-2"])
def test_a_ceiling_below_one_is_refused(tmp_path, monkeypatch, value) -> None:
    """A ceiling of zero would make the surface permanently unavailable, and the
    learner would read *that's the writing done for today* every day."""
    monkeypatch.delenv(KEY, raising=False)
    with pytest.raises(Exception, match="WRITING_MAX_SUBMISSIONS_PER_DAY must be >= 1"):
        config_mod.load_settings(dotenv_path=write_dotenv(tmp_path, **{KEY: value}))

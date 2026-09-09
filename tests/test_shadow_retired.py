"""W14r — the shadow surface is retired, and this is what asserts it.

**A RETIREMENT THAT ONLY A COMMENT RECORDS IS A RETIREMENT THAT COMES BACK.**
#364's own lesson, from the other side: *the plan and the record both said the
right thing and neither was enforced — a claim with no scanner at all.* So the
three halves of this retirement are asserted rather than described:

1. the routes are not served by the application;
2. the Azure door cannot be opened by configuration;
3. **nothing is deleted** — the module, the service, the table and the tests
   are all still here, which is #390's disable-don't-delete precedent and is
   the half a later reader is most likely to undo by "tidying up".

**WHY #376 RETIRED IT, KEPT WITH THE ASSERTIONS SO THE REASON TRAVELS WITH
THEM:** Azure pronunciation assessment detects a word said as a different word
and does not detect an inflectional ending. `model→models`, `window→windows`,
`can→can't` and `validation` were deliberately mispronounced and **only `trust`
was caught**, at 44.0 against neighbours at 97. Inflection and agreement are
most of what a B1→B2 learner gets wrong and most of what the error journal
exists to collect.
"""

from __future__ import annotations

import pytest

from core.config import Settings, load_settings


def test_the_application_serves_no_shadow_route() -> None:
    """The unregistration, asserted on the built app rather than on `main.py`.

    RED against restoring `app.include_router(shadow_router.router)`.
    """
    from apps.api.main import create_app

    # **READ FROM THE OPENAPI SCHEMA, NOT FROM `app.routes`, AND THE FIRST
    # DRAFT GOT THIS WRONG.** This FastAPI version keeps `_IncludedRouter`
    # objects in `app.routes`, whose `.path` is absent — so a scan of that list
    # finds no shadow path **whatever is registered**, and would have passed on
    # a fully restored surface. The schema is what a client can actually reach.
    paths = sorted(create_app().openapi()["paths"])
    assert [p for p in paths if "shadow" in p] == [], (
        "the shadow routes are retired and must not be registered"
    )
    # A sibling proving the app was really built, so an empty path list cannot
    # satisfy the assertion above (#345) — which is exactly how the broken
    # first draft was caught.
    assert "/conversation/turn" in paths


def test_the_startup_log_and_the_registration_still_agree() -> None:
    """#255's defect is what this guards, on the line W14r was editing anyway.

    W13-i registered a router and left it out of the startup log's list, so the
    deploy's own liveness evidence claimed a route set the app did not have.
    **Unregistering from one list and not the other is the same defect
    mirrored**, and it would leave the log advertising a retired surface.
    """
    from pathlib import Path

    source = Path("apps/api/main.py").read_text(encoding="utf-8")
    body = "\n".join(
        line for line in source.splitlines() if not line.strip().startswith("#")
    )
    assert "shadow_router" not in body, (
        "shadow_router must appear in neither the registration nor the log list"
    )


def test_no_configuration_can_open_the_azure_door() -> None:
    """**The fields are gone from `Settings`, so a stale `.env` cannot reach
    the provider.**

    This is the mechanism the retirement actually rests on: not a flag, but the
    absence of anywhere to load the credentials into.
    """
    assert not hasattr(load_settings(), "azure_speech_key")
    assert not hasattr(load_settings(), "azure_speech_region")
    with pytest.raises(TypeError):
        Settings(
            database_url="postgresql://x/y",
            telegram_bot_token="",
            llm_api_key="k",
            azure_speech_key="anything",  # type: ignore[call-arg]
        )


def test_the_outbound_path_refuses_under_real_settings() -> None:
    """And the refusal happens **before any request is constructed.**"""
    from core import speech

    with pytest.raises(speech.SpeechError):
        speech.assess_pronunciation(b"audio", "a reference", settings=load_settings())


def test_nothing_was_deleted() -> None:
    """**#390's precedent, asserted rather than promised.**

    `speech_attempts` holds real measurements of a real voice and dropping a
    table is permanent; the tests are the evidence the surface worked. **The
    likeliest way this retirement goes wrong is somebody tidying up**, so the
    things that must survive are named here and a deletion fails this test.
    """
    from pathlib import Path

    for path in (
        "apps/api/routers/shadow.py",
        "packages/core/services/shadow_score.py",
        "packages/core/speech_api.py",
        "migrations/024_speech_attempts.sql",
        "tests/test_shadow_route.py",
        "tests/test_shadow_line.py",
        "tests/test_shadow_consent_gate.py",
        "tests/test_speech_pronunciation.py",
    ):
        assert Path(path).is_file(), f"{path} must not be deleted (#390)"

    # And no rollback exists to be run by accident.
    assert not list(Path("migrations").glob("*rollback*024*"))


def test_the_voice_gate_still_fails_closed_under_its_new_name() -> None:
    """**A rename on a fail-closed gate is the risk this slice carries.**

    `SHADOW_ALLOWED_USER_IDS` became `VOICE_ALLOWED_USER_IDS` because the
    surface it named no longer exists and the gate it holds does. **A
    half-applied rename closes `/talk`'s microphone rather than opening it** —
    the safe direction, and still a surprise, which is why the deploy sets the
    new variable before removing the old one.

    RED against a default of "everybody" or a fallback to the old name.
    """
    from core.services.conversations import voice_allowed_for

    assert load_settings().voice_allowed_user_ids == ()
    assert voice_allowed_for(1) is False

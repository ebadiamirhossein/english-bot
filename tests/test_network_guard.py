"""The suite may not reach the internet, and this proves the guard enforcing it.

CLAUDE.md §3 rule 4: a green test over an unreachable path proves nothing. The
session-wide guard in ``conftest.py`` currently never fires — which is the
desired state and also indistinguishable, from the outside, from a guard that
cannot fire. These tests make the difference observable.

The guard exists because W2 found a test dialling
``acct123.r2.cloudflarestorage.com`` after a temp ``.env`` leaked fake R2 keys
into ``os.environ``. Nothing happened, because those credentials were fake. The
server's ``.env`` holds five real ones with Object Read & Write on the bucket
that contains every off-site copy of the error journal.
"""

from __future__ import annotations

import socket

import pytest

from tests.support.netguard import OutboundNetworkBlocked, is_local


def test_the_guard_refuses_a_non_loopback_address() -> None:
    """The case that matters: a real host, refused before a packet is sent.

    Uses a documentation-reserved address (RFC 5737) so that a regression which
    somehow bypassed the guard would still not reach anything real.
    """
    with pytest.raises(OutboundNetworkBlocked) as caught:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.1)
            sock.connect(("192.0.2.1", 443))
    message = str(caught.value)
    assert "192.0.2.1" in message
    # The message has to name the test, or a CI failure is a scavenger hunt.
    assert "test_the_guard_refuses_a_non_loopback_address" in message


def test_the_guard_refuses_connect_ex_too() -> None:
    """``connect_ex`` returns an error code instead of raising, so a guard that
    only wrapped ``connect`` would let a whole second API through silently."""
    with pytest.raises(OutboundNetworkBlocked):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.1)
            sock.connect_ex(("192.0.2.1", 443))


def test_loopback_still_works() -> None:
    """PostgreSQL is on 127.0.0.1 — the guard must not break the whole suite.

    Connecting to a closed loopback port raises ``ConnectionRefusedError``, not
    ``OutboundNetworkBlocked``: the point is that the guard let the attempt
    through to the operating system.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        with pytest.raises((ConnectionRefusedError, OSError)) as caught:
            sock.connect(("127.0.0.1", 9))
    assert not isinstance(caught.value, OutboundNetworkBlocked)


@pytest.mark.parametrize(
    "address,expected",
    [
        (("127.0.0.1", 5432), True),
        (("127.0.0.53", 53), True),
        (("::1", 5432), True),
        (("localhost", 5432), True),
        ("/var/run/postgresql/.s.PGSQL.5432", True),
        (("10.0.0.1", 443), False),
        (("192.0.2.1", 443), False),
        (("2001:db8::1", 443), False),
        (("api.anthropic.com", 443), False),
        (("acct123.r2.cloudflarestorage.com", 443), False),
    ],
)
def test_what_counts_as_local(address: object, expected: bool) -> None:
    """The classifier itself, including the address that started this.

    A unix-socket path is a string, not a host, and must stay allowed —
    PostgreSQL is reachable that way and blocking it would break the suite for
    a reason that has nothing to do with the internet.
    """
    assert is_local(address) is expected

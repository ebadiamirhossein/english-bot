"""Refuse any socket connection from the test suite that is not loopback.

**Why.** W2 found a test dialling ``acct123.r2.cloudflarestorage.com`` after a
temp ``.env`` leaked its fake R2 keys into ``os.environ``. Nothing happened,
because those credentials were fake — but the leak was the accident and the
*reachability* is the defect. The server's ``.env`` holds five real ``R2_*``
keys with Object Read & Write on the bucket that contains every off-site copy of
the error journal, and ``pytest -q`` sits in the verification path. The same
leak on a different machine does not fail harmlessly; it authenticates.

This is known issue #70's boundary crossed in the opposite direction: #70 is
open because stubs cannot prove a provider contract, and this would be a test
proving one by accident, against production credentials.

**What it does not cover:** sockets opened by a *child process*. The R2 shell
tests run ``bash`` and a stubbed ``aws`` through ``subprocess``, and that is
also the path the observed incident actually took. Those tests put a recording
``aws`` stub on ``PATH`` for exactly this reason, and that remains the mechanism
there. Named so this guard is not mistaken for complete.

Lives in ``tests/support/`` rather than in ``conftest.py`` so that there is
exactly one :class:`OutboundNetworkBlocked` class object: pytest imports
``conftest`` as a top-level module, while a test importing ``tests.conftest``
would get a second, unrelated copy — and ``pytest.raises`` would not match it.
"""

from __future__ import annotations

import ipaddress
import os
import socket

_LOOPBACK_NAMES = frozenset({"localhost", "localhost.localdomain", ""})


class OutboundNetworkBlocked(RuntimeError):
    """A test tried to connect to something that is not loopback."""


def is_local(address: object) -> bool:
    """True for loopback TCP/UDP and for AF_UNIX paths.

    PostgreSQL on 127.0.0.1 — or over a unix socket, whose address is a plain
    path string rather than a host — keeps working. Everything else is refused.
    """
    # AF_UNIX: the address is a filesystem path, never a host.
    if isinstance(address, (str, bytes)):
        return True
    if not isinstance(address, tuple) or not address:
        # Unknown address family — refuse rather than guess.
        return False

    host = address[0]
    if isinstance(host, bytes):
        host = host.decode("utf-8", "replace")
    if not isinstance(host, str):
        return False
    if host.lower() in _LOOPBACK_NAMES:
        return True
    try:
        # Strip any IPv6 zone index (fe80::1%en0) before parsing.
        return ipaddress.ip_address(host.split("%", 1)[0]).is_loopback
    except ValueError:
        # An unresolved hostname. By the time connect() is called this is
        # almost always already an IP; a name here is something a unit test has
        # no business dialling.
        return False


def install() -> tuple:
    """Patch ``socket.socket``. Returns what :func:`uninstall` needs."""
    real_connect = socket.socket.connect
    real_connect_ex = socket.socket.connect_ex

    def _refuse(address: object) -> None:
        current = os.environ.get("PYTEST_CURRENT_TEST", "<unknown test>")
        raise OutboundNetworkBlocked(
            f"{current} tried to connect to {address!r}. Unit tests may reach "
            "loopback only. If a test needs a provider, stub it — a suite that "
            "can open a socket can, with the wrong environment leaked into it, "
            "authenticate against the bucket holding every off-site copy of "
            "the error journal."
        )

    def guarded_connect(self, address, *args, **kwargs):
        if not is_local(address):
            _refuse(address)
        return real_connect(self, address, *args, **kwargs)

    def guarded_connect_ex(self, address, *args, **kwargs):
        # connect_ex returns an error code rather than raising, so a guard that
        # wrapped only connect() would leave a second API wide open.
        if not is_local(address):
            _refuse(address)
        return real_connect_ex(self, address, *args, **kwargs)

    socket.socket.connect = guarded_connect
    socket.socket.connect_ex = guarded_connect_ex
    return real_connect, real_connect_ex


def uninstall(saved: tuple) -> None:
    socket.socket.connect, socket.socket.connect_ex = saved

"""The one door to Wikidata and Wikimedia Commons. W13d.

**The fourth named HTTP exemption in `packages/core`** (after `video_api.py`,
`speech_api.py` and `push_api.py`), written into `tests/test_core_boundary.py`
by name for their reason: one declared door per external provider.

**NOTHING HERE IS BILLED, AND NOTHING HERE RUNS FOR A LEARNER.** Wikimedia's
APIs are free; they are called only by the human-run
`python -m core.images.bank`, never by a route. A learner's browser fetches a
picture from OUR API (`GET /lexeme-images/{id}.{ext}`), so no learner request
ever reaches Wikimedia and no third party sees a learner's address.

**THE TERMS THIS FOLLOWS, QUOTED IN `data/LICENCES.md` (W13d):**

- the User-Agent policy — *"Scripts should use an informative User-Agent string
  with contact information, or they may be blocked without notice"*; so a live
  run REQUIRES `--contact`, and there is no default contact to go stale;
- the Robot policy, action API unauthenticated — *"keep the concurrency of your
  requests to 1 at a time, and below 5 requests per second overall"*; so
  requests are serial with `PAUSE_SECONDS` between them, and a `429`'s
  `Retry-After` is waited out (bounded) before asking again;
- the Robot policy, media — *"Only use originals or one of our standard
  thumbnail sizes"*; so every download is `THUMB_WIDTH`.

NOTHING HERE IS CALLED DURING A TEST: `tests/conftest.py`'s network guard fails
any socket to a non-loopback address, and the functions are exercised through
`httpx.MockTransport` against responses recorded from the live APIs on
2026-09-25 (`tests/fixtures/commons/`).
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable

import httpx

from core.images import THUMB_WIDTH

WIKIDATA_API = "https://www.wikidata.org/w/api.php"
COMMONS_API = "https://commons.wikimedia.org/w/api.php"

#: Serial requests, one second apart: well inside *"below 5 requests per second"*.
PAUSE_SECONDS = 1.0

_TIMEOUT = httpx.Timeout(30.0, connect=10.0)

#: API:Etiquette's recommended value, in seconds of replication lag.
MAXLAG = 5
#: How many times a `429` or a `maxlag` refusal is waited out before the run stops.
RETRIES = 5
#: When the server names no `Retry-After`.
_DEFAULT_RETRY_AFTER = 5.0


def _retry_after(response: httpx.Response) -> float:
    try:
        return max(1.0, min(60.0, float(response.headers.get("Retry-After", ""))))
    except ValueError:
        return _DEFAULT_RETRY_AFTER


_EXTMETADATA = "|".join(
    [
        "LicenseShortName",
        "LicenseUrl",
        "Artist",
        "Attribution",
        "AttributionRequired",
        "Restrictions",
    ]
)


class CommonsError(Exception):
    """Wikimedia answered in a way the run must not guess past (a 429, a 5xx,
    a body without the expected shape). The run stops; nothing is written."""


@dataclass(frozen=True, slots=True)
class FileInfo:
    title: str
    source_url: str
    sha1: str
    mime: str
    thumb_url: str
    thumb_width: int
    thumb_height: int
    extmetadata: dict[str, str]


def user_agent(contact: str) -> str:
    """The policy's format: ``<client>/<version> (<contact>) <library>/<version>``."""
    contact = contact.strip()
    if not contact:
        raise ValueError("a contact is required by Wikimedia's User-Agent policy")
    return f"english-bot-image-bank/1.0 ({contact}) httpx/{httpx.__version__}"


class CommonsClient:
    """Serial, paced and identified. One instance per run."""

    def __init__(
        self,
        contact: str,
        *,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._http = httpx.Client(
            headers={"User-Agent": user_agent(contact), "Accept-Encoding": "gzip"},
            timeout=_TIMEOUT,
            transport=transport,
            follow_redirects=True,
        )
        self._sleep = sleep
        self._first = True
        self.requests = 0

    def close(self) -> None:
        self._http.close()

    def _get(self, url: str, params: dict[str, Any] | None = None) -> httpx.Response:
        """One paced request.

        **A 429 is waited out, as the Robot policy asks** — *"When we reply
        with a 429 Too Many Requests status code respect the delay specified by
        the Retry-After header"* — at most `RETRIES` times. The first draft
        stopped on any 429; the first live run (2026-09-25) drew
        `429, retry-after: 4` from Wikidata on its ninth request at one per
        second, so stopping would have made every real run die part-way. **A
        5xx still stops:** the policy asks for a 15-minute pause, which a
        human-run command leaves to the human.
        """
        for attempt in range(RETRIES + 1):
            if not self._first:
                self._sleep(PAUSE_SECONDS)
            self._first = False
            self.requests += 1
            response = self._http.get(url, params=params)
            if response.status_code == 429 and attempt < RETRIES:
                self._sleep(_retry_after(response))
                continue
            if response.status_code == 429 or response.status_code >= 500:
                raise CommonsError(f"{url} answered {response.status_code}; stopping")
            if response.status_code != 200:
                raise CommonsError(f"{url} answered {response.status_code}")
            return response
        raise AssertionError("unreachable")

    def _json(self, url: str, params: dict[str, Any]) -> dict[str, Any]:
        """One API read, honouring `maxlag`.

        **Found by the first live call, 2026-09-25, and no mock would have
        found it:** Wikidata answered `{"error": {"code": "maxlag"}}` to the
        very first search — its replicas were more than 5 s behind. `maxlag` is
        API:Etiquette's own mechanism for a bot to yield while the servers are
        busy, and the documented response is to wait `Retry-After` and ask
        again. So a `maxlag` error waits and retries, at most `RETRIES`
        times, and then stops like any other refusal.

        **And Wikidata is not sent `maxlag` at all**, found by the same call:
        its refusal read `"type": "wikibase-queryservice"`, `lag` 6.27 s —
        Wikidata folds the SPARQL query service's lag into `maxlag`, while its
        database replicas read ~1.0 s (`meta=siteinfo&siprop=dbrepllag`). These
        are two cheap read calls that never touch the query service, and five
        waits of five seconds all refused. `maxlag` stays on Commons, where it
        measures the database the reads actually hit.
        """
        extra: dict[str, Any] = {"format": "json"}
        if url != WIKIDATA_API:
            extra["maxlag"] = MAXLAG
        for attempt in range(RETRIES + 1):
            response = self._get(url, {**params, **extra})
            body = response.json()
            error = body.get("error") if isinstance(body, dict) else None
            if error is None:
                return body
            if error.get("code") != "maxlag" or attempt == RETRIES:
                raise CommonsError(f"{url}: {error.get('code', 'error')}")
            self._sleep(_retry_after(response))
        raise AssertionError("unreachable")

    # --- Wikidata --------------------------------------------------------

    def item_for(self, lemma: str) -> str | None:
        """The Wikidata item whose English label IS the lemma, exactly.

        **Exact and lower-case, not the top hit**, measured 2026-09-25: the top
        hit for *spoon* is an American rock band, for *ladder* a 1982 video
        game and for *elbow* an English band. The item labelled `spoon`
        (lower-case) is the utensil, because Wikidata labels common nouns in
        lower case and proper names in title case.
        """
        body = self._json(
            WIKIDATA_API,
            {
                "action": "wbsearchentities",
                "language": "en",
                "uselang": "en",
                "type": "item",
                "limit": 10,
                "search": lemma,
            },
        )
        for hit in body.get("search", []):
            if hit.get("label") == lemma:
                return hit.get("id")
        return None

    def images_of(self, qid: str) -> list[str]:
        """The item's P18 ("image") values, as Commons file names, in order."""
        body = self._json(
            WIKIDATA_API, {"action": "wbgetclaims", "entity": qid, "property": "P18"}
        )
        names: list[str] = []
        for claim in body.get("claims", {}).get("P18", []):
            value = claim.get("mainsnak", {}).get("datavalue", {}).get("value")
            if isinstance(value, str) and value:
                names.append(value)
        return names

    # --- Commons ---------------------------------------------------------

    def file_info(self, name: str) -> FileInfo | None:
        """One file's licence metadata, SHA-1 and a standard-width thumbnail URL."""
        title = name if name.startswith("File:") else f"File:{name}"
        body = self._json(
            COMMONS_API,
            {
                "action": "query",
                "formatversion": 2,
                "titles": title,
                "prop": "imageinfo",
                "iiprop": "url|extmetadata|mime|sha1",
                "iiurlwidth": THUMB_WIDTH,
                "iiextmetadatafilter": _EXTMETADATA,
            },
        )
        pages = body.get("query", {}).get("pages", [])
        if not pages or pages[0].get("missing") or not pages[0].get("imageinfo"):
            return None
        page = pages[0]
        info = page["imageinfo"][0]
        try:
            return FileInfo(
                title=page["title"],
                source_url=info["descriptionurl"],
                sha1=info["sha1"],
                mime=info["mime"],
                thumb_url=info["thumburl"],
                thumb_width=int(info["thumbwidth"]),
                thumb_height=int(info["thumbheight"]),
                extmetadata={
                    key: str(entry.get("value", ""))
                    for key, entry in info.get("extmetadata", {}).items()
                },
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise CommonsError(f"imageinfo for {title} lacks {exc}") from exc

    def download(self, url: str) -> bytes:
        """The thumbnail's bytes. Only ever a URL `file_info` returned."""
        if not url.startswith("https://upload.wikimedia.org/") and not url.startswith(
            "https://thumb.wikimedia.org/"
        ):
            raise CommonsError(f"refusing to download from {url.split('/')[2]}")
        return self._get(url).content

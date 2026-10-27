import httpx
import pytest

from mtg_rebuilder.api import scryfall_client
from mtg_rebuilder.api.scryfall_client import (
    ScryfallClient,
    ScryfallQueryError,
    SearchResult,
)


@pytest.fixture(autouse=True)
def _no_throttle(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(scryfall_client, "SCRYFALL_RATE_LIMIT_SECONDS", 0.0)
    monkeypatch.setattr(scryfall_client, "SEARCH_RETRY_DELAYS", (0.0, 0.0))
    monkeypatch.setattr(scryfall_client, "SEARCH_MIN_INTERVAL_SECONDS", 0.0)


def _client(handler) -> ScryfallClient:
    return ScryfallClient(
        httpx.Client(
            base_url="https://api.scryfall.test",
            transport=httpx.MockTransport(handler),
        )
    )


def _pages(pages: list[list[str]], total_cards: int):
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        page = int(request.url.params["page"])
        seen.append(request.url.params["q"])
        ids = pages[page - 1]
        return httpx.Response(
            200,
            json={
                "total_cards": total_cards,
                "has_more": page < len(pages),
                "data": [{"oracle_id": oid} for oid in ids],
            },
        )

    return handler, seen


def test_search_walks_every_page_and_reports_progress() -> None:
    pages = [[f"p{n}-{i}" for i in range(3)] for n in range(1, 21)]
    handler, seen = _pages(pages, total_cards=175 * 20)
    progress: list[tuple[int, int]] = []

    result = _client(handler).search_oracle_ids_in(
        "otag:ramp", {"p1-0", "p20-2", "not-there"}, on_page=lambda p, t: progress.append((p, t))
    )

    # Past the old 15-page cap: page 20 is still read.
    assert result == SearchResult({"p1-0", "p20-2"}, 175 * 20)
    assert len(seen) == 20
    assert set(seen) == {"otag:ramp"}
    assert progress[0] == (1, 20)
    assert progress[-1] == (20, 20)


def test_search_stops_once_every_owned_card_matched() -> None:
    pages = [["a", "x"], ["b", "y"], ["z"]]
    handler, seen = _pages(pages, total_cards=5)

    result = _client(handler).search_oracle_ids_in("t:creature", {"a", "b"})

    assert result.oracle_ids == {"a", "b"}
    assert len(seen) == 2


def test_search_cancel_returns_partial_result() -> None:
    pages = [["a"], ["b"], ["c"]]
    handler, seen = _pages(pages, total_cards=3)
    calls = {"n": 0}

    def should_stop() -> bool:
        calls["n"] += 1
        return calls["n"] > 1

    result = _client(handler).search_oracle_ids_in(
        "t:creature", {"a", "b", "c"}, should_stop=should_stop
    )

    assert result.cancelled is True
    assert result.oracle_ids == {"a"}
    assert len(seen) == 1


def test_search_no_match_is_empty_not_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"object": "error", "details": "none"})

    result = _client(handler).search_oracle_ids_in("otag:nothing", {"a"})

    assert result.oracle_ids == set()
    assert result.cancelled is False


def test_search_bad_query_raises_with_scryfall_details() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400,
            json={"object": "error", "details": "All of your terms were ignored."},
        )

    with pytest.raises(ScryfallQueryError, match="All of your terms were ignored"):
        _client(handler).search_oracle_ids_in("zzz:", {"a"})


def test_search_network_error_propagates_after_retries() -> None:
    attempts = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["n"] += 1
        raise httpx.ConnectError("offline", request=request)

    with pytest.raises(httpx.TransportError):
        _client(handler).search_oracle_ids_in("t:creature", {"a"})
    assert attempts["n"] == 3


def test_search_rides_out_a_dropped_page() -> None:
    attempts = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["n"] += 1
        page = int(request.url.params["page"])
        if page == 2 and attempts["n"] == 2:
            raise httpx.ReadError("Connection reset by peer", request=request)
        return httpx.Response(
            200,
            json={
                "total_cards": 3,
                "has_more": page < 3,
                "data": [{"oracle_id": f"c{page}"}],
            },
        )

    result = _client(handler).search_oracle_ids_in("t:creature", {"c1", "c2", "c3"})

    assert result.oracle_ids == {"c1", "c2", "c3"}
    assert attempts["n"] == 4


def test_search_waits_out_rate_limit() -> None:
    attempts = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["n"] += 1
        if attempts["n"] == 1:
            return httpx.Response(429, headers={"Retry-After": "0"})
        return httpx.Response(
            200,
            json={"total_cards": 1, "has_more": False, "data": [{"oracle_id": "a"}]},
        )

    result = _client(handler).search_oracle_ids_in("t:creature", {"a"})

    assert result.oracle_ids == {"a"}
    assert attempts["n"] == 2


def test_search_stop_during_retry_is_a_cancel() -> None:
    stop = {"now": False}

    def handler(request: httpx.Request) -> httpx.Response:
        stop["now"] = True
        raise httpx.ReadError("reset", request=request)

    result = _client(handler).search_oracle_ids_in(
        "t:creature", {"a"}, should_stop=lambda: stop["now"]
    )

    assert result.cancelled is True


def test_ping_reports_reachability() -> None:
    def ok(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/bulk-data"
        return httpx.Response(200, json={"data": []})

    def down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline", request=request)

    def broken(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    assert _client(ok).ping() is True
    assert _client(down).ping() is False
    assert _client(broken).ping() is False

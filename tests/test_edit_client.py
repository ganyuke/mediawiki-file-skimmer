import asyncio, json, time
from typing import override
import httpx
from api.databags import MediaWikiResult, ResponseStatus
from api.edit_client import MediaWikiEditClient, MediaWikiEditProtocol
import pytest

from app.databags import PublishConfig

JSONPrimitive = str | int | float | bool | None
JSONType = JSONPrimitive | list["JSONType"] | dict[str, "JSONType"]

CONFIG = PublishConfig("summary", "reason", True, True, True, True)

# ── fake async http layer ───────────────────────────────────────────────────
class FakeDriver(MediaWikiEditProtocol):
    """
    Implements MediaWikiEditProtocol:
      • .post() - pops a pre-loaded httpx.Response off a queue
      • .get_csrf_token() - returns OK with a dummy token
    """

    def __init__(self, scripted: list[httpx.Response]):
        self._queue: list[httpx.Response] = scripted

    @override
    async def post(self, data: dict[str, str], override_url: str | None = None) -> httpx.Response:
        if not self._queue:
            raise AssertionError("FakeDriver queue exhausted!")
        resp = self._queue.pop(0)
        print(f"POST {data['action']} → {resp.status_code}")
        return resp

    @override
    async def get_csrf_token(self) -> MediaWikiResult[str]:
        # Always succeeds with a dummy token
        return MediaWikiResult(status=ResponseStatus.OK, data="TESTTOKEN")

# ── helpers to generate canned httpx.Response objects ──────────────────────
def make_json_response(payload: JSONType, status: int = 200) -> httpx.Response:
    return httpx.Response(status, text=json.dumps(payload))

def mw_ok_edit() -> httpx.Response:
    return make_json_response({"edit": {"result": "Success"}}, 200)

def mw_maxlag(info: str = "Waiting for 10s lagged servers") -> httpx.Response:
    return make_json_response({"error": {"code": "maxlag", "info": info}}, 200)

def mw_generic_error(code: str = "permissiondenied") -> httpx.Response:
    return make_json_response({"error": {"code": code, "info": "nope"}}, 200)

# ── simple status printer (simulates GTK idle callback) ─────────────────────
def ui_status(msg: str):
    now = time.strftime("%H:%M:%S")
    print(f"[{now}] UI says: {msg}")

# ── coroutine tests ────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_happy_path():
    print("\n── happy path ──")
    driver = FakeDriver([mw_ok_edit()])
    client = MediaWikiEditClient(driver, asyncio.Event(), on_status=ui_status)

    res = await client.edit_page("File:A.jpg", "new wikitext",CONFIG)
    print("Result:", res.status)

@pytest.mark.asyncio
async def test_maxlag_then_ok():
    print("\n── maxlag then success ──")
    driver = FakeDriver([mw_maxlag(), mw_ok_edit()])
    ev = asyncio.Event()
    client = MediaWikiEditClient(driver, ev, min_interval=0.1, on_status=ui_status)

    res = await client.edit_page("File:B.jpg", "new text", CONFIG)
    print("Result:", res.status)

@pytest.mark.asyncio
async def test_abort_mid_backoff():
    print("\n── abort mid-backoff ──")
    driver = FakeDriver([mw_maxlag(), mw_ok_edit()])
    abort_flag = asyncio.Event()
    client = MediaWikiEditClient(driver, abort_flag, min_interval=0.1, on_status=ui_status)

    # schedule abort in 0.2s (during backoff sleep)
    _ = asyncio.get_event_loop().call_later(0.2, abort_flag.set)

    res = await client.edit_page("File:C.jpg", "text", CONFIG)
    print("Result:", res.status)

# ── run all tests ───────────────────────────────────────────────────────────
if __name__ == "__main__":
    asyncio.run(test_happy_path())
    asyncio.run(test_maxlag_then_ok())
    asyncio.run(test_abort_mid_backoff())

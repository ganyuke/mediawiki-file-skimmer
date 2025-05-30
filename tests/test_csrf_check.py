'''
Test appartus for CSRF check.
'''
import json
from unittest.mock import AsyncMock
import httpx
import pytest

API_URL = "https://example.com/api" # never actually gets used

JSONPrimitive = str | int | float | bool | None
JSONType = JSONPrimitive | list["JSONType"] | dict[str, "JSONType"]

def make_json_response(payload: JSONType, status: int = 200) -> httpx.Response:
    dummy_request = httpx.Request("GET", API_URL)
    return httpx.Response(
        status_code=status,
        text=json.dumps(payload),
        headers={"Content-Type": "application/json"},
        request=dummy_request  # ✅ set this
    )

OK_TOKEN = "abcd1234+\\foobar"
BAD_TOKEN = "+\\"

good_payload: JSONType   = {"query": {"tokens": {"csrftoken": OK_TOKEN}}}
nolog_payload: JSONType  = {"query": {"tokens": {"csrftoken": BAD_TOKEN}}}
weird_payload: JSONType  = {"not": "valid"}
http_error_resp = http_error_resp = httpx.Response(
    503,
    text="Down",
    request=httpx.Request("GET", API_URL)
) # 503 Service Unavailable

from api.http_client import MediaWikiClient
from api.databags import MediaWikiResult, ResponseStatus

@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mock_response, expected_status",
    [
        (make_json_response(good_payload),  ResponseStatus.OK),
        (make_json_response(nolog_payload), ResponseStatus.NOT_LOGGED_IN),
        (make_json_response(weird_payload), ResponseStatus.PARSE_ERROR),
        (http_error_resp,                   ResponseStatus.HTTP_ERROR),
    ],
)
async def test_get_csrf_token_variants(mock_response: httpx.Response,
                                       expected_status: ResponseStatus):
    """
    Patch MediaWikiEditClient.get so it returns `mock_response` instead of
    making a real HTTP call, then verify the status coming out of
    get_csrf_token().
    """
    # 1. create client with a dummy abort flag and no real HTTP dependency
    client = MediaWikiClient(API_URL)

    # 2. monkey-patch .get to return our canned httpx.Response
    client.get = AsyncMock(return_value=mock_response)  # type: ignore

    # 3. call the method and check the status
    result: MediaWikiResult[str] = await client.get_csrf_token()
    assert result.status is expected_status

import asyncio
import time
from typing import Callable, Protocol, TypeVar
import httpx
from pydantic import BaseModel, ValidationError
from api.databags import EditResponse, ErrorResponse, ErrorResult, MediaWikiResult, MoveResponse, ResponseStatus

M = TypeVar("M", bound=BaseModel)

class MediaWikiEditProtocol(Protocol):
    async def post(self, data: dict[str, str], override_url: str | None = None) -> httpx.Response: ...
    async def get_csrf_token(self) -> MediaWikiResult[str]: ...

class MediaWikiEditClient:
    _http_client: MediaWikiEditProtocol
    _abort_event: asyncio.Event
    maxlag: int
    min_interval: float # minimum interval between requests
    max_retries: int # maximum number of request retries before giving up
    backoff_base: float # multiplier for backoff wait time
    max_backoff: float # maximum interval between retries
    _last_action_time: float # time tthat last successful action occured
    on_status: Callable[[str], None] | None # callback for updating UI live
    
    _debug_prefix: str = ""

    def __init__(
        self,
        http_client: MediaWikiEditProtocol,
        abort_event: asyncio.Event,
        maxlag: int = 5,
        min_interval: float = 5.0,
        max_retries: int = 3,
        backoff_base: float = 2.0,
        max_backoff: float = 30.0, # 30 seconds should give enough time for the servers to cool off
        on_status: Callable[[str], None] | None = None
    ):
        self.maxlag = maxlag
        self.min_interval = min_interval
        self.max_retries = max_retries
        self.backoff_base = backoff_base
        self.max_backoff = max_backoff

        self._last_action_time = 0.0
        self._http_client = http_client
        self._abort_event = abort_event
        self.on_status = on_status

    async def _snooze(self, seconds: float) -> bool:
        # hacky interruptible sleep
        start = time.monotonic() # it'd be fun to track this
        try:
            _ = await asyncio.wait_for(self._abort_event.wait(), timeout=seconds)
            print(f"abort detected after waiting for {time.monotonic() - start} seconds (timeout was {seconds}).")
            return True
        except asyncio.TimeoutError:
            return False            

    async def _perform(
        self,
        params: dict[str, str],
        model: type[M] | None = None,
    ) -> MediaWikiResult[M]:
        gap = max(0, self._last_action_time + self.min_interval - time.monotonic())
        if gap:
            if self.on_status:
                self.on_status(f"Delaying next POST by {gap:.2f}s...")
            was_aborted = await self._snooze(seconds=gap)
            if (was_aborted):
                return MediaWikiResult(status=ResponseStatus.ABORTED)

        # exponential backoff per-page
        backoff = self.backoff_base

        for _try in range(1, self.max_retries + 1):
            try:
                resp = await self._http_client.post(data=params)
            except httpx.HTTPError as e:
                return MediaWikiResult(
                    status=ResponseStatus.HTTP_ERROR,
                    data=None,
                    error=ErrorResult(
                        code="http_error",
                        info=str(e)
                    )
                )

            if resp.status_code != 200:
                return MediaWikiResult(
                    status=ResponseStatus.HTTP_ERROR,
                    error=ErrorResult(
                        code="http_status",
                        info=f"{resp.status_code}"
                        )
                    )

            payload = resp.text

            # this assumes that MediaWiki returns in the legacy API error format
            if "error" in payload:
                # this will pick up error ANYWHERE in the payload,
                # but whatever, we'll validate the format so
                try:
                    err_result = ErrorResponse.model_validate_json(payload)
                    if (err_result.error.code == "maxlag"):
                        # it returns 
                        wait = min(backoff, self.max_backoff)
                        if self.on_status:
                            self.on_status(f"Sleeping {wait:.1f}s due to maxlag...")
                        was_aborted = await self._snooze(wait)
                        if (was_aborted):
                            return MediaWikiResult(status=ResponseStatus.ABORTED) 
                        # not aborted? need to retry request after max_lag
                        backoff *= self.backoff_base
                        continue
                    else:
                        return MediaWikiResult(
                            status=ResponseStatus.API_ERROR,
                            error=err_result.error,
                            raw=payload
                        )
                except ValidationError:
                    pass

            # looks like we got a good request
            # so we can process this
            self._last_action_time = time.monotonic()

            if model is None:
                return MediaWikiResult(status=ResponseStatus.OK, raw=payload)

            try:
                parsed = model.model_validate_json(payload)
            except ValidationError:
                return MediaWikiResult(status=ResponseStatus.PARSE_ERROR,raw=payload)

            return MediaWikiResult(status=ResponseStatus.OK, data=parsed, raw=payload)

        # ran out of retries
        return MediaWikiResult(status=ResponseStatus.MAX_LIMIT_HIT, raw=f"exceeded retries: {self.max_retries}")

    async def edit_page(
        self,
        title: str,
        new_text: str,
        summary: str = "",
    ) -> MediaWikiResult[EditResponse]:
        token_result = await self._http_client.get_csrf_token()
        if (token_result.status is not ResponseStatus.OK or token_result.data is None):
            return MediaWikiResult(
                status=ResponseStatus.NO_CSRF
            )

        edit_param = {
            "action": "edit",
            "title": self._debug_prefix + title,
            "text": new_text,
            "summary": summary,
            "minor": "1",
            "bot": "1",
            "token": token_result.data,
            "format": "json",
        }

        return await self._perform(edit_param, EditResponse)

    async def move_page(
        self,
        title: str,
        new_title: str,
        reason: str = "",
    ) -> MediaWikiResult[MoveResponse]:
        token_result = await self._http_client.get_csrf_token()
        if (token_result.status is not ResponseStatus.OK or token_result.data is None):
            return MediaWikiResult(
                status=ResponseStatus.NO_CSRF
            )

        move_param = {
            "action": "move",
            "from":  self._debug_prefix + title,
            "to": self._debug_prefix + new_title,
            "reason": reason,
            "movetalk": "1",
            "movesubpages": "1",
            "noredirect": "0",
            "token": token_result.data,
            "format": "json",
        }
    
        return await self._perform(move_param, MoveResponse)

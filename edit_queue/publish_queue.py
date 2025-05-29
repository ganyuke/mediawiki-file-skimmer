from concurrent.futures import Future
import asyncio, httpx
from pydantic.dataclasses import dataclass

from app.databags import AppDeps

@dataclass(frozen=True)
class PublishPayload:
    original_title: str
    summary: str = ""
    reason: str = ""
    new_title: str | None = None
    new_text: str | None = None

class UploadQueue:
    _deps: AppDeps
    _current_task: asyncio.Task[httpx.Response] | None = None
    _task_ready: Future[asyncio.Task[httpx.Response]] | None = None

    def __init__(self, deps: AppDeps):
        self._deps = deps

    def publish(self, payload: PublishPayload) -> None:
        # prepare a Future to hand the Task back to the caller
        self._task_ready = Future()

        def _spawn():
            # actually run on the right loop
            task = self._deps.event_loop.create_task(self._post(payload))
            if (self._task_ready is None):
                raise RuntimeError("self._task_ready does not exist!")

            # publish the Task so main thread can cancel it
            self._task_ready.set_result(task)
            self._current_task = task

        _ = self._deps.event_loop.call_soon_threadsafe(_spawn)

    async def _post(self, payload: PublishPayload):
        client = self._deps.http_client
        
        if (payload.new_text is not None):
            _success = await client.publish_edit(title=payload.original_title, new_text=payload.new_text, summary=payload.summary)

        if (payload.new_title is not None):
            _success = await client.publish_rename(title=payload.original_title, new_title=payload.new_title, reason=payload.reason)

    def task(self) -> asyncio.Task[httpx.Response]:
        if (self._task_ready is None):
            raise RuntimeError("_task_ready does not exist!")

        # blocks until start() has scheduled the task
        return self._task_ready.result()

    def abort(self) -> None:
        if self._current_task and not self._current_task.done():
            # schedule cancel on the same loop
            _ = self._deps.event_loop.call_soon_threadsafe(self._current_task.cancel)

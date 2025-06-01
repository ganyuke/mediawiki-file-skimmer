import asyncio
from typing import Callable
from api.databags import ResponseStatus
from api.edit_client import MediaWikiEditClient
from app.databags import AppDeps, ModificationPayload, PublishConfig, PublishPayload, PublishStage, StatusState

class UploadQueue:
    _deps: AppDeps
    _panic_button: asyncio.Event
    _running_task: asyncio.Task[None] | None = None
    _delay: float
    _ui_notifier: Callable[[str | None, PublishStage, StatusState, str | None], None]

    def __init__(self, deps: AppDeps, ui_notifier: Callable[[str | None, PublishStage, StatusState, str | None], None]):
        self._deps = deps
        self._panic_button = asyncio.Event()
        self._delay = 8.0
        self._ui_notifier = ui_notifier

    def _notifier(self, title: str | None, stage: PublishStage, status: StatusState, tooltip: str | None = None):
        if (self._ui_notifier is not None):
            self._ui_notifier(title, stage, status, tooltip)

    async def _eat_queue(self, payload: PublishPayload):
        edit_client = MediaWikiEditClient(
            http_client=self._deps.http_client,
            abort_event=self._panic_button,
        )

        for change in payload.changes:
            if self._panic_button.is_set():
                print("abort detected in loop start")
                return
            await self._post(payload=change, config=payload.config, edit_client=edit_client)

        self._notifier(None, PublishStage.DONE, StatusState.INVALID)

    def publish_all(self, payload: PublishPayload) -> None:
        if (len(payload.changes) <= 0):
            # why are you even sending this??
            self._notifier(None, PublishStage.DONE, StatusState.INVALID)
            return
        
        if (self._running_task is not None and not self._running_task.done()):
            # should abort if you want to publish again
            return

        def async_task():
            self._panic_button.clear()
            self._running_task = self._deps.event_loop.create_task(self._eat_queue(payload))
        _ = self._deps.event_loop.call_soon_threadsafe(async_task)

    async def _post(self, payload: ModificationPayload, config: PublishConfig, edit_client: MediaWikiEditClient):
        if (payload.new_text is None and payload.new_title is None):
            # why would the user want to submit a null edit
            self._notifier(payload.original_title, PublishStage.DONE, StatusState.INVALID)
            return
        
        if (payload.new_text is not None):
            self._notifier(payload.original_title, PublishStage.EDIT, StatusState.IN_PROGRESS)

            def notifier(tooltip: str):
                self._notifier(payload.original_title, PublishStage.EDIT, StatusState.DELAYED, tooltip)
            edit_client.on_status = notifier

            result = await edit_client.edit_page(title=payload.original_title, new_text=payload.new_text, config=config)

            match result.status:
                case ResponseStatus.OK:
                    self._notifier(payload.original_title, PublishStage.EDIT, StatusState.OK)
                    return
                case _:
                    self._notifier(payload.original_title, PublishStage.EDIT, StatusState.FAIL)

        if (payload.new_title is not None):
            self._notifier(payload.original_title, PublishStage.MOVE, StatusState.IN_PROGRESS)

            def notifier(tooltip: str):
                self._notifier(payload.original_title, PublishStage.MOVE, StatusState.DELAYED, tooltip)
            edit_client.on_status = notifier

            result = await edit_client.move_page(title=payload.original_title, new_title=payload.new_title, config=config)

            match result.status:
                case ResponseStatus.OK:
                    self._notifier(payload.original_title, PublishStage.MOVE, StatusState.OK)
                    return
                case _:
                    self._notifier(payload.original_title, PublishStage.MOVE, StatusState.FAIL)

    def abort(self) -> None:
        # editing is dangerous. if a call is in flight,
        # we want to know if the API heard it to avoid desync.
        # so we shouldn't use task.cancel() here. instead, we
        # will check explicitly when we can abort.
        _ = self._deps.event_loop.call_soon_threadsafe(self._panic_button.set)

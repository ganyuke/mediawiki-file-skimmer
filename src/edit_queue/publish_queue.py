import asyncio
from types import CoroutineType
from typing import Callable, TypeVar
from api.databags import MediaWikiResult, ResponseStatus
from api.edit_client import MediaWikiEditClient
from app.databags import AppDeps, ModificationPayload, PublishConfig, PublishPayload, PublishStage, StatusState

T = TypeVar("T")

class UploadQueue:
    _deps: AppDeps
    _panic_button: asyncio.Event
    _running_task: asyncio.Task[None] | None = None
    _delay: float
    _status_updater: Callable[[str | None, PublishStage, StatusState, str | None], None]

    def __init__(self, deps: AppDeps, status_updater: Callable[[str | None, PublishStage, StatusState, str | None], None]):
        self._deps = deps
        self._panic_button = asyncio.Event()
        self._delay = 8.0
        self._status_updater = status_updater

    def _notifier(self, title: str | None, stage: PublishStage, status: StatusState, tooltip: str | None = None):
        if (self._status_updater is not None):
            self._status_updater(title, stage, status, tooltip)

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
        original_title = payload.original_title

        if (payload.new_text is None and payload.new_title is None):
            # why would the user want to submit a null edit
            self._notifier(original_title, PublishStage.DONE, StatusState.INVALID)
            return

        done_edit = True
        done_move = True
        
        async def post_to(stage: PublishStage, action: CoroutineType[None, None, MediaWikiResult[T]]) -> bool:
            self._notifier(original_title, stage, StatusState.IN_PROGRESS)

            def notifier(tooltip: str):
                self._notifier(original_title, stage, StatusState.DELAYED, tooltip)
            edit_client.on_status = notifier

            result = await action

            match result.status:
                case ResponseStatus.OK:
                    self._notifier(original_title, stage, StatusState.OK)
                    return True
                case _:
                    self._notifier(original_title, stage, StatusState.FAIL)
            
            return False

        stage = PublishStage.EDIT
        if (payload.new_text is not None):
            cort = edit_client.edit_page(title=original_title, new_text=payload.new_text, config=config)
            done_edit =await post_to(stage, cort)
        else:
            self._notifier(original_title, stage, StatusState.NOT_SCHEDULED)

        stage = PublishStage.MOVE
        if (payload.new_title is not None):
            cort = edit_client.move_page(title=original_title, new_title=payload.new_title, config=config)
            done_move = await post_to(stage, cort)
        else:
            self._notifier(original_title, stage, StatusState.NOT_SCHEDULED)            

        stage = PublishStage.DONE
        if done_edit and done_move:
            final_status = StatusState.OK
        else:
            final_status = StatusState.FAIL

        self._notifier(original_title, stage, final_status)

    def abort(self) -> None:
        # editing is dangerous. if a call is in flight,
        # we want to know if the API heard it to avoid desync.
        # so we shouldn't use task.cancel() here. instead, we
        # will check explicitly when we can abort.
        _ = self._deps.event_loop.call_soon_threadsafe(self._panic_button.set)

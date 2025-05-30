from dataclasses import dataclass, field
from api.api import MediaWikiDataService
from api.databags import DataPage
from edit_queue.edits import EntryMod, ModificationTracker

@dataclass(frozen=True)
class PresentationData:
    title: str
    original: DataPage
    wikitext: str = ""
    image_path: str = ""
    linked_pages: list[str] = field(default_factory=list)
    is_staged: bool = False
    is_submitted: bool = False

class QueueManager:
    mediawiki_data_service: MediaWikiDataService
    modification_tracker: ModificationTracker
    submit_list: set[str]
    staged_list: set[str]
    seen_list: set[str]
    queue_list: list[str]
    queue_position: int | None = None

    def __init__(self, mediawiki_data_service: MediaWikiDataService, modification_tracker: ModificationTracker):
        self.mediawiki_data_service = mediawiki_data_service
        self.modification_tracker = modification_tracker

        self.submit_list = set()
        self.staged_list = set()
        self.seen_list = set()
        self.queue_list = list()

    def _append_unique(self, pages: list[str]):
        for page in pages:
            if (page not in self.seen_list):
                self.queue_list.append(page)
                self.seen_list.add(page)

    def _merge_pages(self, title: str) -> PresentationData:
        original_data = self.mediawiki_data_service.get_page(title)
        if (original_data is None):
            raise RuntimeError("Queue found non-existent page.")

        wikitext: str = original_data.wikitext
        is_staged: bool = title in self.staged_list
        is_submitted: bool = title in self.submit_list
        changedData: EntryMod | None = self.modification_tracker.modifications.get(title)
        if (changedData is not None):
            if (changedData.title is not None):
                title = changedData.title
            if (changedData.wikitext is not None):
                wikitext = changedData.wikitext

        presentable = PresentationData(title, original_data, wikitext, original_data.image_path, list(original_data.linked_pages), is_staged, is_submitted)
        return presentable

    def current_page(self) -> PresentationData | None:
        if (self.queue_position is not None):
            selectedTitle = self.queue_list[self.queue_position]
            return self._merge_pages(selectedTitle)

    def can_prev(self) -> bool:
        if (self.queue_position is not None and self.queue_position > 0):
            return True
        return False

    def can_next(self) -> bool:
        if (self.queue_position is not None and self.queue_position < len(self.queue_list) - 1):
            return True
        return False

    def prev(self) :
        if (self.queue_position is not None and self.can_prev()):
            self.queue_position -= 1

    def next(self):
        if (self.queue_position is not None and self.can_next()):
            self.queue_position += 1

    def jump_to(self, position: int) -> bool:
        if (self.queue_position is None or len(self.queue_list) < position):
            return False
        self.queue_position = position
        return True

    async def get_batch(self):
        result = await self.mediawiki_data_service.batch_category()
        title_list = [page.title for page in result.pages]
        self._append_unique(title_list)

        if (self.queue_position is None and len(self.queue_list) > 0):
            self.queue_position = 0

        return result.complete

    def set_entry_staged(self, target_title: str, mark_as_staged: bool = True):
        if (mark_as_staged):
            self.staged_list.add(target_title)
        else:
            self.staged_list.remove(target_title)

    def mark_entry_submitted(self, target_title: str):
        self.staged_list.add(target_title)

    def get_staged_pages(self) -> list[str]:
        return [title for title in self.queue_list if title in self.staged_list]
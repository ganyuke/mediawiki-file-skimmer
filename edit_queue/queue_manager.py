from pydantic import Field
from pydantic.dataclasses import dataclass
from api.api import CategoryBatcher, DataPage
from edit_queue.edits import EntryMod, ModificationTracker

@dataclass
class PresentationData:
    title: str
    original: DataPage
    wikitext: str = ""
    image_path: str = ""
    linked_pages: list[str] = Field(default_factory=list)
    is_modified: bool = False

class QueueManager:
    categoryBatcher: CategoryBatcher
    modificationTracker: ModificationTracker
    queueList: list[str]
    queuePosition: int | None

    def __init__(self, categoryBatcher: CategoryBatcher, modificationTracker: ModificationTracker):
        self.categoryBatcher = categoryBatcher
        self.modificationTracker = modificationTracker
        self.queueList = []
        self.queuePosition = None

    async def _get_next_batch(self):
        # if (self.can_fetch_more()):
            newPages = await self.categoryBatcher.fetch_batch()
            for page in newPages:
                # assume that batches will always be new pages
                self.queueList.append(page.title)

            if (self.queuePosition is None and len(self.queueList) > 0):
                self.queuePosition = 0

    def _merge_pages(self, title: str) -> PresentationData:
        originalData = self.categoryBatcher.pages.get(title)
        if (originalData is None):
            raise RuntimeError("Queue found non-existent page.")

        presentable = PresentationData(title, originalData, originalData.wikitext, originalData.image_path, list(originalData.linked_pages))

        changedData: EntryMod | None = self.modificationTracker.modifications.get(title)
        if (changedData is not None):
            presentable.is_modified = True
            if (changedData.title is not None):
                presentable.title = changedData.title
            if (changedData.wikitext is not None):
                presentable.wikitext = changedData.wikitext

        return presentable

    def current_page(self) -> PresentationData | None:
        if (self.queuePosition is not None):
            selectedTitle = self.queueList[self.queuePosition]
            return self._merge_pages(selectedTitle)

    def can_prev(self) -> bool:
        if (self.queuePosition is not None and self.queuePosition > 0):
            return True
        return False

    def can_next(self) -> bool:
        if (self.queuePosition is not None and self.queuePosition < len(self.queueList) - 1):
            return True
        return False

    def can_fetch_more(self) -> bool:
        return self.categoryBatcher.canContinue()

    def prev(self) :
        if (self.queuePosition is not None and self.can_prev()):
            self.queuePosition -= 1

    def next(self):
        if (self.queuePosition is not None and self.can_next()):
            self.queuePosition += 1

    def jump_to(self, position: int) -> bool:
        if (self.queuePosition is None or len(self.queueList) < position):
            return False
        self.queuePosition = position
        return True

    async def get_batch(self):
        return await self._get_next_batch()
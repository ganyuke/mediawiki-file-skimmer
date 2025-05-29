from typing import Callable, Literal
from pydantic.dataclasses import dataclass

from api.databags import DataPage

@dataclass
class EntryMod:
    title: str | None = None
    wikitext: str | None = None

    def is_empty(self) -> bool:
        return self.title is None and self.wikitext is None

class ModificationTracker:
    modifications: dict[str, EntryMod] = {}
    page_source: Callable[[str], DataPage | None]

    def __init__(self, page_source: Callable[[str], DataPage | None]):
        self.page_source = page_source

    def revert_changes(self, target_title: str):
        _ = self.modifications.pop(target_title, None)

    def _set_field(self, target_title: str, target_field: Literal["title", "wikitext"], new_value: str | None):
        originalData = self.page_source(target_title)
        # If this is None, something crazy must have hapepned.
        if (originalData is None):
            raise RuntimeError(f"No original data for {target_title} — possible state desync (dequeued?)")

        # implicity treat empty strings(already invalid)
        # and shoving in original value as a reset value
        if (new_value == "" or getattr(originalData, target_field) == new_value):
            new_value = None

        mod_entry: EntryMod | None = self.modifications.get(target_title)
        if (mod_entry is None):
            mod_entry = EntryMod()
            self.modifications[target_title] = mod_entry

        setattr(mod_entry, target_field, new_value)
        
        if (new_value is None and mod_entry.is_empty()):
            self.revert_changes(target_title)

    def set_renamed_title(self, target_title: str, new_title: str | None):
        self._set_field(target_title, 'title', new_title)

    def set_altered_body(self, target_title: str, new_body: str | None):
        self._set_field(target_title, 'wikitext', new_body)
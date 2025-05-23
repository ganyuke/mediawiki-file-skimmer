import gi
from app.databags import AppDeps
from app.link_row import SidebarLinkRow
gi.require_version('Gtk', '4.0')
gi.require_version('GdkPixbuf', '2.0')
from gi.repository import GdkPixbuf, Gtk, GLib # pyright: ignore[reportMissingModuleSource]

from edit_queue.queue_manager import PresentationData
from dataclasses import dataclass
from urllib.parse import quote

# data bag for hydrator helper class
@dataclass
class EditorUi:
    image_preview: Gtk.Picture
    page_title_entry: Gtk.Entry
    links_list:  Gtk.ListBox
    wikitext_buffer: Gtk.TextBuffer

class WaterBottle:
    '''
    Hydrator helper class for the main editor
    window. Loads new pages into the UI.
    '''
    _image_cache: dict[str, GdkPixbuf.Pixbuf] = {}
    _deps: AppDeps
    _editor_ui: EditorUi

    def __init__(self, deps: AppDeps, editor_ui: EditorUi):
        self._editor_ui = editor_ui
        self._deps = deps

    def _load_link_list(self, link_list: list[str]):
        self._editor_ui.links_list.remove_all()

        for title in link_list:
            sanitizedTitle = quote(title)
            url = self._deps.app_config.get_wiki_url() + "/" + sanitizedTitle
            row = SidebarLinkRow(title, url)
            self._editor_ui.links_list.append(row)

    async def _set_image_from_url(self, url: str):
        if url in self._image_cache:
            pixbuf = self._image_cache[url]
        else:
            response = await self._deps.http_client.get(url, None)
            _ = response.raise_for_status()
            data = response.content

            loader = GdkPixbuf.PixbufLoader.new()
            _ = loader.write(data)
            _ = loader.close()
            pixbuf = loader.get_pixbuf()

            if (pixbuf is not None):
                self._image_cache[url] = pixbuf

        _ = GLib.idle_add(self._editor_ui.image_preview.set_pixbuf, pixbuf)

    def load_page(self, page: PresentationData):
        _ = self._deps.event_loop.call_soon_threadsafe(
        lambda: self._deps.event_loop.create_task(self._set_image_from_url(page.image_path))
        )
        _ = GLib.idle_add(self._hydrate_interface, page)

    def _hydrate_interface(self, data: PresentationData):
        self._editor_ui.page_title_entry.set_text(data.title)
        self._editor_ui.wikitext_buffer.set_text(data.wikitext)
        self._load_link_list(data.linked_pages)

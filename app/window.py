# pyright: reportAny=false
import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, GLib # pyright: ignore[reportMissingModuleSource]

from app.staging_dialog import StagingDialog
from urllib.parse import quote
from app.link_row import SidebarLinkRow
from api.api import CategoryBatcher, FileUsageBatcher
from edit_queue.edits import ModificationTracker
from edit_queue.queue_manager import QueueManager
from app.databags import AppDeps
from app.page_hydrator import EditorUi, WaterBottle

@Gtk.Template(filename="ui/base_cleaned.ui")
class MediaWikiViewerWindow(Gtk.ApplicationWindow):
    '''
    The main editor window for the application.
    '''
    __gtype_name__: str = "MediaWikiViewerWindow"

    # main controls
    _category_entry: Gtk.Entry = Gtk.Template.Child(name="category_entry")
    _load_btn: Gtk.Button = Gtk.Template.Child(name="load_button")
    _batch_btn: Gtk.Button = Gtk.Template.Child(name="load_batch_button")
    _queue_btn: Gtk.Button = Gtk.Template.Child(name="queue_button")
    _should_rename: Gtk.CheckButton = Gtk.Template.Child(name="should_rename")

    # hydration targets
    _image_preview: Gtk.Picture = Gtk.Template.Child(name="image_preview")
    _page_title_entry: Gtk.Entry = Gtk.Template.Child(name="page_title")
    _links_list:  Gtk.ListBox = Gtk.Template.Child(name="links_list")
    _wikitext_view: Gtk.TextView = Gtk.Template.Child(name="wikitext_view")
    _wikitext_buffer: Gtk.TextBuffer = Gtk.Template.Child(name="wikitext_buffer")

    # navigation
    _previous_btn: Gtk.Button = Gtk.Template.Child(name="previous_page")
    _next_btn: Gtk.Button = Gtk.Template.Child(name="next_page")
    _confirm_btn: Gtk.Button = Gtk.Template.Child(name="confirm_page")

    # pre-run sensitivity zones
    _content_container: Gtk.Box = Gtk.Template.Child(name="content_container")
    _navigation_container: Gtk.Box = Gtk.Template.Child(name="navigation_container")

    # login
    _login_label: Gtk.Label = Gtk.Template.Child(name="login_label")
    _login_button: Gtk.Button = Gtk.Template.Child(name="login_button")

    # spinners
    _async_label: Gtk.Label = Gtk.Template.Child(name="async_label")
    _async_spinner: Gtk.Spinner = Gtk.Template.Child(name="async_spinner")

    # app state
    _queue_manager: QueueManager | None = None
    _deps: AppDeps
    _water_bottle: WaterBottle

    def __init__(self, deps: AppDeps, **kwargs): # pyright: ignore[reportUnknownParameterType, reportMissingParameterType]
        self._deps = deps
        super().__init__(**kwargs) # pyright: ignore[reportUnknownArgumentType]

        editor_ui = EditorUi(
            image_preview=self._image_preview,
            page_title_entry=self._page_title_entry,
            links_list=self._links_list,
            wikitext_buffer=self._wikitext_buffer,
            rename_button=self._should_rename
            )

        self._water_bottle = WaterBottle(deps, editor_ui)

    def set_loading_indicator(self, is_spinner_enable: bool, label_text: str | None = None):
        self._async_spinner.set_visible(is_spinner_enable)
        if (label_text):
            self._async_label.set_visible(True)
            self._async_label.set_text(label_text)
        else:
            self._async_label.set_visible(False)

    def set_nav_buttons(self, prev_on: bool, next_on: bool):
        self._previous_btn.set_sensitive(prev_on)
        self._next_btn.set_sensitive(next_on)

    def _update_move_btns(self):
        if (self._queue_manager is None):
            return

        canPrev = self._queue_manager.can_prev()
        canNext = self._queue_manager.can_next()

        _ = GLib.idle_add(self.set_nav_buttons, canPrev, canNext)

    def _hydrate_current(self):
        if (self._queue_manager is None):
            return

        self._update_move_btns()
        data = self._queue_manager.current_page()
        if (data is not None):
            _ = GLib.idle_add(self.set_staging_status, data.is_staged)
            self._water_bottle.load_page(data, self._construct_link_list(data.linked_pages))

    async def _load_batch(self):
        button = self._load_btn
        if (self._queue_manager is None):
            _ = GLib.idle_add(button.set_sensitive, True)
            return

        _ = GLib.idle_add(self.set_loading_indicator, True, "Fetching batch...")
        complete = await self._queue_manager.get_batch()
        if (not complete):
            _ = GLib.idle_add(self.set_loading_indicator, False, "Batch incomplete! Limit hit!")
        else:
            _ = GLib.idle_add(self.set_loading_indicator, False)
        _ = GLib.idle_add(self._batch_btn.set_sensitive, self._queue_manager.can_fetch_more())
        self._hydrate_current()

    async def _setup_category(self, category: str):
        def create_query_manager(category: str):
            isStart = self._queue_manager is None

            category_batcher: CategoryBatcher = CategoryBatcher(
                category=category,
                client=self._deps.http_client
                )
            fileusage_batcher: FileUsageBatcher = FileUsageBatcher(self._deps.http_client)
            modification_tracker: ModificationTracker = ModificationTracker(category_batcher.pages)
            self._queue_manager = QueueManager(category_batcher, fileusage_batcher, modification_tracker)

            if (isStart):
                def desensitize():
                    self._content_container.set_sensitive(True)
                    self._navigation_container.set_sensitive(True)
                _ = GLib.idle_add(desensitize)

        is_category_valid = await self._deps.http_client.check_category_valid(category)

        if (is_category_valid):
            create_query_manager(category)
            await self._load_batch()
        else:
            def set_error():
                self._category_entry.set_icon_from_icon_name(Gtk.EntryIconPosition.PRIMARY, "dialog-warning-symbolic")
                self._category_entry.get_style_context().add_class("error")
            _ = GLib.idle_add(set_error)

    async def _on_login_clicked(self):

        def login(user: str):
            loginString = f"Logged in as <b>{user}</b>"
            self._login_label.set_label(loginString)
            self._login_label.show()
            self._login_button.set_label("Logout")
        def logout():
            self._login_label.hide()
            self._login_button.set_label("Login")

        if (not self._deps.http_client.is_logged_in()):
            _ = GLib.idle_add(self.set_loading_indicator, True, "Logging in...")
            config = self._deps.app_config.config
            user_info = await self._deps.http_client.login(config.bot_username, config.bot_password)
            if (user_info is not None):
                _ = GLib.idle_add(login, user_info.name)
        else:
            _ = GLib.idle_add(self.set_loading_indicator, True, "Logging out...")
            success = await self._deps.http_client.logout()
            if (success):
                _ = GLib.idle_add(logout)
        
        _ = GLib.idle_add(self.set_loading_indicator, False)        

    def _construct_link_list(self, link_list: list[str]) -> list[SidebarLinkRow]:
        rows: list[SidebarLinkRow] = []

        def replace_title(_: SidebarLinkRow, new_title: str):
            if (self._queue_manager is None):
                return
            current_page = self._queue_manager.current_page()
            if (current_page is None):
                return
            original_title: str = current_page.original.title 
            title_pieces: list[str] = original_title.split(".")
            suffix = title_pieces.pop()
            suffix = suffix.lower()
            file_title = f'File:{new_title.strip()}.{suffix}'
            self._should_rename.set_active(True)
            self._page_title_entry.set_text(file_title)

        def paste_link(_: SidebarLinkRow, link_title: str):
            link_text = f'[[{link_title}]]'
            insert_mark = self._wikitext_buffer.get_insert()
            insert_iter = self._wikitext_buffer.get_iter_at_mark(insert_mark)
            self._wikitext_buffer.insert(insert_iter, link_text)

        for title in link_list:
            sanitizedTitle = quote(title)
            url = self._deps.app_config.get_wiki_url() + "/" + sanitizedTitle
            row = SidebarLinkRow(title, url)
            _ = row.connect("request_rename", replace_title)
            _ = row.connect("request_paste", paste_link)

            rows.append(row)
        
        return rows

    @Gtk.Template.Callback(name="on_category_changed")
    def on_category_changed(self, field: Gtk.Entry):
        text = field.get_text()
        self._load_btn.set_sensitive(bool(text.strip()))
        def clear_error():
            self._category_entry.set_icon_from_icon_name(Gtk.EntryIconPosition.PRIMARY, "text-editor-symbolic")
            self._category_entry.get_style_context().remove_class("error")
        _ = GLib.idle_add(clear_error)

    @Gtk.Template.Callback(name="on_load_clicked")
    def on_load_clicked(self, _: Gtk.Button):
        category = self._category_entry.get_text()
        category = category.strip()

        def async_trigger():
            _ = self._deps.event_loop.create_task(self._setup_category(category))
        __ = self._deps.event_loop.call_soon_threadsafe(async_trigger)


    @Gtk.Template.Callback(name="on_load_batch_clicked")
    def on_load_batch_clicked(self, button: Gtk.Button):
        button.set_sensitive(False)

        def async_trigger():
            _ = self._deps.event_loop.create_task(self._load_batch())
        _ = self._deps.event_loop.call_soon_threadsafe(async_trigger)

    # stubbed because it will upset the gtk template parser
    # if i don't define handle ALL the signals
    @Gtk.Template.Callback(name="open_queue")
    def open_queue(self, _: Gtk.Button):
        pass

    @Gtk.Template.Callback(name="on_login_clicked")
    def on_login_clicked(self, _: Gtk.Button):
        def async_trigger():
            _ = self._deps.event_loop.create_task(self._on_login_clicked())
        __ = self._deps.event_loop.call_soon_threadsafe(async_trigger)

    @Gtk.Template.Callback(name="on_rename_toggled")
    def on_rename_toggled(self, button: Gtk.CheckButton):
        if (self._queue_manager is None):
            return

        if (not button.get_active()):
            currPage = self._queue_manager.current_page()
            if (currPage is not None):
                originalTitle = currPage.original.title
                self._queue_manager.modification_tracker.set_renamed_title(originalTitle, None)
                self._page_title_entry.set_text(originalTitle)

    @Gtk.Template.Callback(name="on_file_name_changed")
    def on_file_name_changed(self, entry: Gtk.Entry):
        if (self._queue_manager is None):
            return
        current_page = self._queue_manager.current_page()
        if (current_page is None):
            return
        original_title = current_page.original.title 
        text = entry.get_text()
        self._queue_manager.modification_tracker.set_renamed_title(original_title, text)

    @Gtk.Template.Callback(name="on_wikitext_changed")
    def on_wikitext_changed(self, buffer: Gtk.TextBuffer):
        if (self._queue_manager is None):
            return
        current_page = self._queue_manager.current_page()
        if (current_page is None):
            return
        original_title = current_page.original.title 
        start = buffer.get_start_iter()
        end = buffer.get_end_iter()
        text = buffer.get_text(start, end, include_hidden_chars=True)
        self._queue_manager.modification_tracker.set_altered_body(original_title, text)

    @Gtk.Template.Callback(name="on_prev_clicked")
    def on_prev_clicked(self, _: Gtk.Button):
        if (self._queue_manager is None):
            return

        self._queue_manager.prev()
        self._hydrate_current()

    @Gtk.Template.Callback(name="on_next_clicked")
    def on_next_clicked(self, _: Gtk.Button):
        if (self._queue_manager is None):
            return

        self._queue_manager.next()
        self._hydrate_current()

    def set_staging_status(self, mark_as_staged: bool):
        if (mark_as_staged):
            self._confirm_btn.add_css_class('flat')
            self._confirm_btn.remove_css_class("suggested-action")
            self._confirm_btn.set_label("Unstage")

            self._content_container.set_sensitive(False)
        else:
            self._confirm_btn.add_css_class('suggested-action')
            self._confirm_btn.remove_css_class("flat")
            self._confirm_btn.set_label("Stage")

            self._content_container.set_sensitive(True)

    @Gtk.Template.Callback(name="on_confirm_clicked")
    def on_confirm_clicked(self, _btn: Gtk.Button):
        if (self._queue_manager is None):
            return
        current_page = self._queue_manager.current_page()
        if (current_page is None):
            return
        original_title = current_page.original.title 
        original_text = current_page.original.wikitext

        if (current_page.is_staged):
            self._queue_manager.set_entry_staged(original_title, False)
            self.set_staging_status(False)
        else:
            modified_title = current_page.title
            modified_text = current_page.wikitext

            if (modified_title == original_title):
                modified_title = None
            if (modified_text == original_text):
                modified_text = None

            def stage_content(_dialog: StagingDialog):
                if (self._queue_manager is None):
                    return
                self._queue_manager.set_entry_staged(original_title)
                self.set_staging_status(True)

            dialog = StagingDialog(self, original_title, original_text, modified_title, modified_text)
            _ = dialog.connect('confirmed', stage_content)
            dialog.present()

    @Gtk.Template.Callback(name="on_publish_clicked")
    def on_publish_clicked(self, _btn: Gtk.Button):
        pass
# pyright: reportAny=false
import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, GLib # pyright: ignore[reportMissingModuleSource]

from api.api import CategoryBatcher
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
            wikitext_buffer=self._wikitext_buffer
            )

        self._water_bottle = WaterBottle(deps, editor_ui)

    def _load_current(self):
        if (self._queue_manager is None):
            return

        self._update_move_btns()
        data = self._queue_manager.current_page()
        if (data is not None):
            self._water_bottle.load_page(data)

    async def _load_batch(self):
        button = self._load_btn
        if (self._queue_manager is None):
            _ = GLib.idle_add(button.set_sensitive, True)
            return

        await self._queue_manager.get_batch()
        _ = GLib.idle_add(self._batch_btn.set_sensitive, self._queue_manager.can_fetch_more())
        self._load_current()
    
    def _create_query_manager(self, category: str):
        isStart = self._queue_manager is None

        categoryBatcher: CategoryBatcher = CategoryBatcher(
            base_url=self._deps.app_config.get_api_url(),
            category=category,
            client=self._deps.http_client
            )
        modificationTracker: ModificationTracker = ModificationTracker(categoryBatcher.pages)
        self._queue_manager = QueueManager(categoryBatcher, modificationTracker)

        if (isStart):
            def desensitize():
                self._content_container.set_sensitive(True)
                self._navigation_container.set_sensitive(True)
            _ = GLib.idle_add(desensitize)
            
    async def _check_category(self, category: str):
        is_valid = await self._deps.http_client.check_category_valid(category)
        if (is_valid):
            self._create_query_manager(category)
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
            config = self._deps.app_config.config
            user_info = await self._deps.http_client.login(config.bot_username, config.bot_password)
            if (user_info is not None):
                _ = GLib.idle_add(login, user_info.name)
        else:
            success = await self._deps.http_client.logout()
            if (success):
                _ = GLib.idle_add(logout)

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
            _ = self._deps.event_loop.create_task(self._check_category(category))
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
        print("queue opened")

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
                self._queue_manager.modificationTracker.set_renamed_title(originalTitle, None)
                self._page_title_entry.set_text(originalTitle)

    def _update_move_btns(self):
        if (self._queue_manager is None):
            return

        canPrev = self._queue_manager.can_prev()
        _ = GLib.idle_add(self._previous_btn.set_sensitive, canPrev)

        canNext = self._queue_manager.can_next()
        _ = GLib.idle_add(self._next_btn.set_sensitive, canNext)

    @Gtk.Template.Callback(name="on_file_name_changed")
    def on_file_name_changed(self, entry: Gtk.Entry):
        if (self._queue_manager is None):
            return
        currPage = self._queue_manager.current_page()
        if (currPage is None):
            return
        title = currPage.title 
        text = entry.get_text()
        self._queue_manager.modificationTracker.set_renamed_title(title, text)

    @Gtk.Template.Callback(name="on_wikitext_changed")
    def on_wikitext_changed(self, buffer: Gtk.TextBuffer):
        if (self._queue_manager is None):
            return
        currPage = self._queue_manager.current_page()
        if (currPage is None):
            return
        title = currPage.title 
        start = buffer.get_start_iter()
        end = buffer.get_end_iter()
        text = buffer.get_text(start, end, include_hidden_chars=True)
        self._queue_manager.modificationTracker.set_altered_body(title, text)

    @Gtk.Template.Callback(name="on_prev_clicked")
    def on_prev_clicked(self, _: Gtk.Button):
        if (self._queue_manager is None):
            return

        self._queue_manager.prev()
        self._load_current()

    @Gtk.Template.Callback(name="on_next_clicked")
    def on_next_clicked(self, _: Gtk.Button):
        if (self._queue_manager is None):
            return

        self._queue_manager.next()
        self._load_current()
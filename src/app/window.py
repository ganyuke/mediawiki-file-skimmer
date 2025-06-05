# pyright: reportAny=false
import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, GLib # pyright: ignore[reportMissingModuleSource]

from app.publish_dialog import PublishDialog
from edit_queue.publish_queue import UploadQueue
from app.controller import AppStateController
from app.staging_dialog import StagingDialog
from urllib.parse import quote
from app.link_row import SidebarLinkRow
from api.api import MediaWikiDataService
from edit_queue.edits import ModificationTracker
from edit_queue.queue_manager import QueueManager
from app.databags import (
    AppDeps,
    AsyncIndicators,
    AuthError,
    AutofillBody,
    AutofillRename,
    FailedBatchLoad,
    HydrateCurrent,
    CategoryUpdated,
    EditorUi,
    EditorWidgets,
    EndAsync,
    InteractableAreas,
    LinkedPagesUi,
    LoginControls,
    LoginOK,
    LogoutOK,
    Msg,
    NavigationControls,
    PublishPayload,
    PublishStage,
    StagingUpdated,
    StartAsync,
    StatusState,
    Thaw,
    TopLevelControls
)

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

    _linked_load_button: Gtk.Button = Gtk.Template.Child(name="linked_load_button")
    _publish_button: Gtk.Button = Gtk.Template.Child(name="publish_pages")
    _right_edit_panel: Gtk.Box = Gtk.Template.Child(name="pane_right")
    _file_entry_container: Gtk.Box = Gtk.Template.Child(name="file_entry_container")

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
    _state_controller: AppStateController
    _publish_dialog: PublishDialog | None = None
    _publish_handler: UploadQueue | None = None

    def __init__(self, deps: AppDeps, **kwargs): # pyright: ignore[reportUnknownParameterType, reportMissingParameterType]
        self._deps = deps
        super().__init__(**kwargs) # pyright: ignore[reportUnknownArgumentType]

        editor_widgets = EditorWidgets(
            async_ind=AsyncIndicators(label=self._async_label, spinner=self._async_spinner),
            editor_ui=EditorUi(
            image_preview=self._image_preview,
            page_title_entry=self._page_title_entry,
            wikitext_buffer=self._wikitext_buffer,
            rename_checkbox=self._should_rename
            ),
            linked_ui=LinkedPagesUi(
                links_list=self._links_list,
                links_fetch_button=self._linked_load_button
            ),
            nav_ctrls=NavigationControls(
                next_button=self._next_btn,
                prev_button=self._previous_btn,
                stage_button=self._confirm_btn,
                publish_button=self._publish_button
            ),
            tl_ctrls=TopLevelControls(
                category_entry=self._category_entry,
                category_load_button=self._load_btn,
                batch_load_button=self._batch_btn,
                queue_open_button=self._queue_btn
            ),
            login_ctrls=LoginControls(
                login_label=self._login_label,
                login_button=self._login_button
            ),
            int_areas=InteractableAreas(
                content_container=self._content_container,
                navigation_container=self._navigation_container,
                right_edit_panel=self._right_edit_panel,
                file_entry_container=self._file_entry_container
            )
        )

        self._state_controller = AppStateController(deps, editor_widgets)

    def _append_to_buffer(self, append_text: str):
        insert_mark = self._wikitext_buffer.get_insert()
        insert_iter = self._wikitext_buffer.get_iter_at_mark(insert_mark)
        self._wikitext_buffer.insert(insert_iter, append_text)

    def _dispatch(self, msg: Msg):
        if isinstance(msg, AutofillBody):
            self._append_to_buffer(msg.append_text)
            return

        new = self._state_controller.reduce(msg)
        _ = GLib.idle_add(self._state_controller.render, new)

    def _hydrate_current(self):
        if (self._queue_manager is None):
            return

        data = self._queue_manager.current_page()
        if (data is not None):
            original_title = data.original.title
            more_usage = self._queue_manager.mediawiki_data_service.can_continue_fu(original_title)
            can_continue = self._queue_manager.mediawiki_data_service.can_continue_cat()
            self._dispatch(HydrateCurrent(
                can_prev=self._queue_manager.can_prev(),
                can_next=self._queue_manager.can_next(),
                title=data.title,
                wikitext=data.wikitext,
                image_url=data.image_path,
                links=self._construct_link_list(data.linked_pages),
                staged=data.is_staged,
                renamed=original_title != data.title,
                more_usage=more_usage,
                more_batch=can_continue
            ))

    async def _load_batch(self):
        if (self._queue_manager is None):
            self._dispatch(FailedBatchLoad("Queue manager does not exist!"))
            return
        self._dispatch(StartAsync("Fetching batch..."))
        complete = await self._queue_manager.get_batch()

        # TODO: distinguish incomplete batch from completed
        if (not complete):
            pass
        
        self._hydrate_current()

    async def _setup_category(self, category: str):
        def create_query_manager(category: str):
            is_start = self._queue_manager is None
            mediawiki_data_service: MediaWikiDataService = MediaWikiDataService(self._deps.http_client, category)
            modification_tracker: ModificationTracker = ModificationTracker(mediawiki_data_service.get_page)
            self._queue_manager = QueueManager(mediawiki_data_service, modification_tracker)

            if (is_start):
                self._dispatch(Thaw())

        is_category_valid = await self._deps.http_client.check_category_valid(category)

        if (is_category_valid):
            create_query_manager(category)
            await self._load_batch()
        else:
            self._dispatch(CategoryUpdated(False))

    async def _on_login_clicked(self):
        is_logged_in = self._deps.http_client.is_logged_in()
        self._dispatch(StartAsync("Logging in..." if not is_logged_in
                        else "Logging out..."))

        if (not is_logged_in):
            config = self._deps.app_config.config
            user_info = await self._deps.http_client.login(config.bot_username, config.bot_password)
            if (user_info is not None):
                self._dispatch(LoginOK(user_info.name))
            else:
                self._dispatch(AuthError("Failed to login."))
        else:
            success = await self._deps.http_client.logout()
            if (success):
                self._dispatch(LogoutOK())
            else:
                self._dispatch(AuthError("Failed to logout."))
        
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

            self._dispatch(AutofillRename(file_title))

        def paste_link(_: SidebarLinkRow, link_title: str):
            link_text = f'[[{link_title}]]'

            self._dispatch(AutofillBody(link_text))

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
        not_empty = bool(text.strip())
        if (not_empty):
            self._dispatch(CategoryUpdated(True))
        else:
            self._dispatch(CategoryUpdated(False))

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

    async def _linked_load(self):
        if (self._queue_manager is None):
            return
        current_page = self._queue_manager.current_page()
        if (current_page is None):
            return
        original_title = current_page.original.title

        self._dispatch(StartAsync("Loading file usages..."))
        result = await self._queue_manager.mediawiki_data_service.batch_file_usage(original_title)

        if (result is not None):
            self._hydrate_current()
        else:
            self._dispatch(EndAsync())

    @Gtk.Template.Callback(name="on_linked_load_clicked")
    def on_linked_load_clicked(self, _btn: Gtk.Button):
        def async_trigger():
            _ = self._deps.event_loop.create_task(self._linked_load())
        __ = self._deps.event_loop.call_soon_threadsafe(async_trigger)

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
            self._dispatch(StagingUpdated(False, original_title != current_page.title))
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
                self._dispatch(StagingUpdated(True, original_title != current_page.title))

            dialog = StagingDialog(self, original_title, original_text, modified_title, modified_text)
            _ = dialog.connect('confirmed', stage_content)
            dialog.present()

    @Gtk.Template.Callback(name="on_publish_clicked")
    def on_publish_clicked(self, _btn: Gtk.Button):
        if (self._queue_manager is None):
            return

        dialog = self._publish_dialog
        if (dialog is None):
            dialog = PublishDialog(self)
            self._publish_dialog = dialog

            def status_updater(title: str | None, stage: PublishStage, status: StatusState | None, override_tooltip: str | None):
                def buffer():
                    if (self._queue_manager is None):
                        return
                    if (title is not None and stage == PublishStage.DONE and status == StatusState.OK):
                        self._queue_manager.mark_entry_submitted(title)

                    dialog.update_child(title, stage, status, override_tooltip)

                _ = GLib.idle_add(buffer)

            publish_queue = self._publish_handler
            if (publish_queue is None):
                publish_queue = UploadQueue(deps=self._deps, status_updater=status_updater)
                self._publish_handler = publish_queue

            def publish(_dialog: PublishDialog):
                if (self._queue_manager is None):
                    return
                payloads = self._queue_manager.get_staged_payloads()
                config = dialog.get_publish_config()
                publish_payload = PublishPayload(changes=payloads, config=config)
                publish_queue.publish_all(publish_payload)

            def abort(_dialog: PublishDialog):
                publish_queue.abort()

            _ = dialog.connect("confirmed", publish)
            _ = dialog.connect("aborted", abort)

        dialog.generate_children(self._queue_manager.get_staged_pages())
        dialog.show()
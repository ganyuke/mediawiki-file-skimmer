import gi
gi.require_version('Gtk', '4.0')
gi.require_version('GdkPixbuf', '2.0')
from gi.repository import GLib, GdkPixbuf, Gtk # pyright: ignore[reportMissingModuleSource]

from dataclasses import replace
from app.databags import (
    AppDeps,
    AppState,
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
    StagingUpdated,
    StartAsync,
    Thaw,
    TopLevelControls
)

class AppStateController:
    _state: AppState

    _async_ind: AsyncIndicators
    _editor_ui: EditorUi
    _linked_ui: LinkedPagesUi
    _nav_ctrls: NavigationControls
    _tl_ctrls: TopLevelControls
    _login_ctrls: LoginControls
    _int_areas: InteractableAreas

    _deps: AppDeps
    _image_cache: dict[str, GdkPixbuf.Pixbuf]

    def __init__(self, deps: AppDeps, editor_widgets: EditorWidgets):
        self._state = AppState()
        self._deps = deps
        self._image_cache = {}

        self._async_ind = editor_widgets.async_ind
        self._editor_ui = editor_widgets.editor_ui
        self._linked_ui = editor_widgets.linked_ui
        self._nav_ctrls = editor_widgets.nav_ctrls
        self._tl_ctrls = editor_widgets.tl_ctrls
        self._login_ctrls = editor_widgets.login_ctrls
        self._int_areas = editor_widgets.int_areas

    def reduce(self, msg: Msg) -> AppState:
        state = self._state
        match msg:
            case HydrateCurrent(
                can_prev=prev,
                can_next=next,
                title=new_title,
                wikitext=new_wikitext,
                image_url=new_url,
                links=new_links,
                staged=is_staged,
                renamed=is_renamed,
                more_usage=can_fetch_usage,
                more_batch=can_fetch_batch
            ):
                return replace(state,
                    can_prev=prev,
                    can_next=next,
                    title=new_title,
                    wikitext=new_wikitext,
                    image_url=new_url,
                    linked_pages=new_links,
                    staged=is_staged,
                    renamed=is_renamed,
                    more_usage=can_fetch_usage,
                    more_batch=can_fetch_batch,
                    loading_label=None
                )
            case StartAsync(label):
                return replace(state, 
                    loading_label = label
                )
            case EndAsync():
                return replace(state,
                    loading_label = None
                )
            case LoginOK(user):
                return replace(state,
                    logged_in_user = user,
                    loading_label = None
                )
            case LogoutOK():
                return replace(state,
                    logged_in_user = None,
                    loading_label = None
                )
            case AuthError(message):
                print(message)
                return replace(state,
                    loading_label = None
                )
            case CategoryUpdated(validity):
                return replace(state,
                    invalid_category = not validity
                )
            case AutofillRename(new_title):
                return replace(state,
                    renamed = True,
                    title = new_title
                )
            case AutofillBody():
                return state
            case Thaw():
                return replace(state,
                    cold_start = False
                )
            case FailedBatchLoad():
                return state
            case StagingUpdated(status, is_renamed):
                return replace(state,
                    staged = status,
                    renamed = is_renamed
                )

    async def _set_image_from_url(self, url: str):
        if url in self._image_cache:
            pixbuf = self._image_cache[url]
        else:
            response = await self._deps.http_client.get(None, override_url=url)
            _ = response.raise_for_status()
            data = response.content

            loader = GdkPixbuf.PixbufLoader.new()
            _ = loader.write(data)
            _ = loader.close()
            pixbuf = loader.get_pixbuf()

            if (pixbuf is not None):
                self._image_cache[url] = pixbuf

        _ = GLib.idle_add(self._editor_ui.image_preview.set_pixbuf, pixbuf)

    def _set_staging_status(self, mark_as_staged: bool):
        stage_btn = self._nav_ctrls.stage_button

        if (mark_as_staged):
            stage_btn.add_css_class('flat')
            stage_btn.remove_css_class("suggested-action")
            stage_btn.set_label("Unstage")
        else:
            stage_btn.add_css_class('suggested-action')
            stage_btn.remove_css_class("flat")
            stage_btn.set_label("Stage")

        self._int_areas.right_edit_panel.set_sensitive(not mark_as_staged)
        self._int_areas.file_entry_container.set_sensitive(not mark_as_staged)

    def render(self, new: AppState) -> None:
        old = self._state
        self._state = new

        # COLD START
        if old.cold_start != new.cold_start:
            self._int_areas.content_container.set_sensitive(new.cold_start)
            self._int_areas.navigation_container.set_sensitive(new.cold_start)

        # CATEGORY ENTRY
        if old.invalid_category != new.invalid_category:
            category_entry = self._tl_ctrls.category_entry
            load_button = self._tl_ctrls.category_load_button
            load_button.set_sensitive(not new.invalid_category)
            if (new.invalid_category):
                category_entry.set_icon_from_icon_name(Gtk.EntryIconPosition.PRIMARY, "dialog-warning-symbolic")
                category_entry.get_style_context().add_class("error")
            else:
                category_entry.set_icon_from_icon_name(Gtk.EntryIconPosition.PRIMARY, "text-editor-symbolic")
                category_entry.get_style_context().remove_class("error")

        # AUTHENTICATION
        if old.logged_in_user != new.logged_in_user:
            login_button = self._login_ctrls.login_button
            login_label = self._login_ctrls.login_label
            
            if new.logged_in_user:
                login_label.set_label(
                    f"Logged in as <b>{new.logged_in_user}</b>")
                login_label.show()
                login_button.set_label("Logout")
            else:
                login_label.hide()
                login_button.set_label("Login")

            logged_in = new.logged_in_user is not None
            self._nav_ctrls.publish_button.set_sensitive(logged_in)
            if (logged_in):
                publish_tooltip = "Publish changes to MediaWiki remote"
            else:
                publish_tooltip = "Log in before publishing"
            self._nav_ctrls.publish_button.set_tooltip_text(publish_tooltip)

        # STAGING
        if old.staged != new.staged:
            # Content area should be disabled on staged files
            # Stage button turns into "Unstage" button
            self._set_staging_status(new.staged)
        if old.submitted != new.submitted:
            # Content area should be permanently disabled on submitted files
            # Stage button should be disabled on submitted files
            should_be_editable = not new.submitted and not new.staged
            self._int_areas.content_container.set_sensitive(should_be_editable)
            self._nav_ctrls.stage_button.set_sensitive(not new.submitted)

        # ASYNC INDICATORS
        # spinner should always appears when the label is there
        # no label, why even show the spinner?
        if old.loading_label != new.loading_label:
            async_in_progress = new.loading_label is not None
            self._async_ind.spinner.set_visible(async_in_progress)
            self._async_ind.label.set_visible(async_in_progress)
            if new.loading_label:
                self._async_ind.label.set_text(new.loading_label)

        # TOP LEVEL BUTTONS
        self._tl_ctrls.batch_load_button.set_sensitive(new.more_batch)

        # NAVIGATION BUTTONS
        # should be individually disabled when queue cannot move forward/backward
        if old.can_prev != new.can_prev:
            self._nav_ctrls.prev_button.set_sensitive(new.can_prev)
        if old.can_next != new.can_next:
            self._nav_ctrls.next_button.set_sensitive(new.can_next)

        # MAIN EDITOR PANEL
        # hydrate main panel
        if old.title != new.title:
            self._editor_ui.page_title_entry.set_text(new.title)
        if old.wikitext != new.wikitext:
            self._editor_ui.wikitext_buffer.set_text(new.wikitext)

        # I can't be bothered to keep track of the actual checkbox state
        # So might as well just pave over it when we need to
        rename_checkbox = self._editor_ui.rename_checkbox
        is_rename_checked = rename_checkbox.get_active()
        if (is_rename_checked != new.renamed):
            self._editor_ui.rename_checkbox.set_active(new.renamed)

        # LINKED PAGES PANEL
        # we constructed the rows in the main window for access to functions
        if (old.linked_pages != new.linked_pages) or (old.staged != new.staged):
            self._linked_ui.links_list.remove_all()
            for row in new.linked_pages:
                row.set_button_status(not new.staged)
                self._linked_ui.links_list.append(row)
        if old.more_usage != new.more_usage:
            self._linked_ui.links_fetch_button.set_sensitive(new.more_usage)

        # IMAGE PANEL
        # we have to delagate this to an async call since we
        # don't have the image yet
        # This is a holdover from the old WaterBottle class.
        if old.image_url != new.image_url:
            def fetch_image():
                _ = self._deps.event_loop.create_task(self._set_image_from_url(new.image_url))
            _ = self._deps.event_loop.call_soon_threadsafe(fetch_image)
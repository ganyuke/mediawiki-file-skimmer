import gi
gi.require_version('Gtk', '4.0')
gi.require_version('GdkPixbuf', '2.0')
from gi.repository import Gtk # pyright: ignore[reportMissingModuleSource]

import asyncio
from dataclasses import dataclass, field
from api.http_client import MediaWikiClient
from app.link_row import SidebarLinkRow
from config import AppConfig

@dataclass
class AppDeps:
    app_config: AppConfig
    http_client: MediaWikiClient
    event_loop: asyncio.AbstractEventLoop

@dataclass(frozen=True)
class HydrateCurrent:
    can_prev: bool
    can_next: bool
    title: str
    wikitext: str
    image_url: str
    links: list[SidebarLinkRow]
    staged: bool
    renamed: bool
    more_usage: bool
    more_batch: bool

@dataclass(frozen=True)
class StartAsync:
    label: str

@dataclass(frozen=True)
class EndAsync:
    pass

@dataclass(frozen=True)
class LoginOK:
    user: str

@dataclass(frozen=True)
class LogoutOK: 
    pass

@dataclass(frozen=True)
class AuthError:
    message: str

@dataclass(frozen=True)
class CategoryUpdated:
    validity: bool

@dataclass(frozen=True)
class AutofillRename:
    new_title: str

@dataclass(frozen=True)
class AutofillBody:
    append_text: str

@dataclass(frozen=True)
class Thaw:
    pass

@dataclass(frozen=True)
class FailedBatchLoad:
    reason: str

@dataclass(frozen=True)
class StagingUpdated:
    status: bool

Msg = HydrateCurrent | StartAsync | EndAsync | LoginOK | LogoutOK | AuthError | CategoryUpdated | AutofillRename | AutofillBody | Thaw | FailedBatchLoad | StagingUpdated

@dataclass(frozen=True)
class AppState:
    # navigation
    can_prev: bool = False
    can_next: bool = False
    # current page
    title: str = ""
    wikitext: str = ""
    image_url: str = ""
    linked_pages: list[SidebarLinkRow] = field(default_factory=list)
    renamed: bool = False
    # bottom controls
    staged: bool = False
    submitted: bool = False
    invalid_category: bool = True
    # async flags
    loading_label: str | None = None
    # global flags
    cold_start: bool = True
    logged_in_user: str | None = None
    # cont flags
    more_batch: bool = False
    more_usage: bool = False

@dataclass(frozen=True)
class AsyncIndicators:
    label: Gtk.Label
    spinner: Gtk.Spinner

@dataclass(frozen=True)
class EditorUi:
    image_preview: Gtk.Picture
    page_title_entry: Gtk.Entry
    wikitext_buffer: Gtk.TextBuffer
    rename_checkbox: Gtk.CheckButton

@dataclass(frozen=True)
class LinkedPagesUi:
    links_list:  Gtk.ListBox
    links_fetch_button: Gtk.Button

@dataclass(frozen=True)
class NavigationControls:
    next_button: Gtk.Button
    prev_button: Gtk.Button
    stage_button: Gtk.Button
    publish_button: Gtk.Button

@dataclass(frozen=True)
class TopLevelControls:
    category_entry: Gtk.Entry
    category_load_button: Gtk.Button
    batch_load_button: Gtk.Button
    queue_open_button: Gtk.Button

@dataclass(frozen=True)
class LoginControls:
    login_label: Gtk.Label
    login_button: Gtk.Button

@dataclass(frozen=True)
class InteractableAreas:
    content_container: Gtk.Box
    navigation_container: Gtk.Box

@dataclass(frozen=True)
class EditorWidgets:
    async_ind: AsyncIndicators
    editor_ui: EditorUi
    linked_ui: LinkedPagesUi
    nav_ctrls: NavigationControls
    tl_ctrls: TopLevelControls
    login_ctrls: LoginControls
    int_areas: InteractableAreas
    
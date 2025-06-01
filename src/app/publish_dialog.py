# pyright: reportAny=false
import gi
gi.require_version('Gtk', '4.0')
from gi.repository import GObject, Gtk # pyright: ignore[reportMissingModuleSource]

from app.databags import STATUS_ICONS, PublishConfig, PublishStage, StatusState
from app.publish_row import PublishRow

@Gtk.Template(filename="ui/publish_modal.ui")
class PublishDialog(Gtk.Window):
    '''
    Template for dialog shown when publishing changes.
    '''
    __gtype_name__: str = "MediaWikiPublishDialog"
    __gsignals__: dict[str, tuple[int, None | type, tuple[type, ...]]] = {
        "confirmed": (GObject.SignalFlags.RUN_FIRST, PublishConfig, ()),
        "aborted": (GObject.SignalFlags.RUN_FIRST, None, ())
    }

    _cancel_btn: Gtk.Button = Gtk.Template.Child(name="cancel-publish-button")
    _confirm_btn: Gtk.Button = Gtk.Template.Child(name="confirm-publish-button")

    _publish_review_panel: Gtk.Box = Gtk.Template.Child(name="publish-review-panel")
    _publish_review_listbox: Gtk.ListBox = Gtk.Template.Child(name="publish-review-listbox")

    _edit_reason_container: Gtk.Box = Gtk.Template.Child(name="edit-reason-container")
    _edit_reason_entry: Gtk.Entry = Gtk.Template.Child(name="edit-reason-entry")

    _move_reason_container: Gtk.Box = Gtk.Template.Child(name="move-reason-container")
    _move_reason_entry: Gtk.Entry = Gtk.Template.Child(name="move-reason-entry")

    _minor_edit_checkbox: Gtk.CheckButton = Gtk.Template.Child(name="minor-edit-checkbox")

    _move_options_container: Gtk.Box = Gtk.Template.Child(name="move-options-container")
    _move_talk_checkbox: Gtk.CheckButton = Gtk.Template.Child(name="move-talk-checkbox")
    _move_subpage_checkbox: Gtk.CheckButton = Gtk.Template.Child(name="move-subpage-checkbox")
    _leave_redirect_checkbox: Gtk.CheckButton = Gtk.Template.Child(name="leave-redirect-checkbox")

    _row_tracker: dict[str, PublishRow]
    _publish_started: bool = False

    def __init__(self, parent: Gtk.Window):
        super().__init__()
        self.set_transient_for(parent)

        _ = self._cancel_btn.connect("clicked", self.on_cancel)
        _ = self._confirm_btn.connect("clicked", self.on_confirm)

        self._row_tracker = {}

    def generate_children(self, pages: list[str]):
        for row in self._row_tracker.values():
            self._publish_review_listbox.remove(row)
        self._row_tracker.clear()

        for row in pages:
            title = row
            item = PublishRow(title)
            self._publish_review_listbox.append(item)
            self._row_tracker[title] = item
        
    def update_child(self, title: str | None, stage: PublishStage, status: StatusState | None, override_tooltip: str | None):
        if (title is None or status is None):
            return # TODO: handle finished queue
        visual = STATUS_ICONS[status]

        if (override_tooltip is not None):
            visual.tooltip = override_tooltip

        item = self._row_tracker.get(title)
        if (item is None):
            raise RuntimeError(f"Got an update request for a non-existent PublishRow with title {title}.")
        item.set_status(stage, visual)

    def on_cancel(self, _button: Gtk.Button) -> None:
        self.hide()

    def on_confirm(self, _button: Gtk.Button) -> None:
        if (self._publish_started):
            self.emit("aborted")
            self._publish_started = False
            _button.set_label("Publish")
        else:
            self.emit("confirmed", PublishConfig)
            self._publish_started = True
            _button.set_label("Abort")

    def get_publish_config(self) -> PublishConfig:
        return PublishConfig(
            edit_summary=self._edit_reason_entry.get_text(),
            move_reason=self._move_reason_entry.get_text(),
            minor_edit=self._minor_edit_checkbox.get_active(),
            move_talk=self._move_talk_checkbox.get_active(),
            move_subpage=self._move_subpage_checkbox.get_active(),
            leave_redirect=self._leave_redirect_checkbox.get_active(),
        )
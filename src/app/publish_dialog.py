# pyright: reportAny=false
import gi
gi.require_version('Gtk', '4.0')
from gi.repository import GObject, Gtk # pyright: ignore[reportMissingModuleSource]

from pydantic.dataclasses import dataclass

@dataclass(frozen=True)
class PublishPayload:
    original_title: str
    new_title: str | None = None
    new_text: str | None = None

@Gtk.Template(filename="ui/publish_modal.ui")
class PublishDialog(Gtk.Window):
    '''
    Template for dialog shown when publishing changes.
    '''
    __gtype_name__: str = "publish-dialog"
    __gsignals__: dict[str, tuple[int, None | type, tuple[type, ...]]] = {
        "confirmed": (GObject.SignalFlags.RUN_FIRST, None, ()),
        "published": (GObject.SIGNAL_RUN_FIRST, None, (str,))
    }

    _cancel_btn: Gtk.Button = Gtk.Template.Child(name="cancel-publish-button")
    _confirm_btn: Gtk.Button = Gtk.Template.Child(name="confirm-publish-button")

    def __init__(self, parent: Gtk.Window, original_title: str, original_text: str, modified_title: str | None, modified_text: str | None):
        super().__init__()
        self.set_transient_for(parent)

        _ = self._cancel_btn.connect('clicked', self.on_cancel)
        _ = self._confirm_btn.connect('clicked', self.on_confirm)

    def generate_children(self, list: list[PublishPayload]):
        pass

    def on_cancel(self, _button: Gtk.Button) -> None:
        self.hide()

    def on_confirm(self, _button: Gtk.Button) -> None:
        self.emit("confirmed")
        self.hide()
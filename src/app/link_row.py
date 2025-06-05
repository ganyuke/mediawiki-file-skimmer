# pyright: reportAny=false
import gi
gi.require_version('Gtk', '4.0')
from gi.repository import GObject, Gtk, GLib # pyright: ignore[reportMissingModuleSource]
 
@Gtk.Template(filename="ui/linked_item.ui")
class SidebarLinkRow(Gtk.ListBoxRow):
    '''
    Template for entries in the linked pages list.
    '''
    __gtype_name__: str = "SidebarLinkRow"
    __gsignals__: dict[str, tuple[int, None | type, tuple[type, ...]]] = {
        "request-rename": (GObject.SignalFlags.RUN_FIRST, None, (str,)),
        "request-paste": (GObject.SignalFlags.RUN_FIRST, None, (str,)),
    }

    _title: str
    _link_label: Gtk.Label = Gtk.Template.Child(name="link_label")
    _rename_button: Gtk.Button = Gtk.Template.Child(name="rename_select_button")
    _link_paste_button: Gtk.Button = Gtk.Template.Child(name="link_paste_button")

    def rename_select_button_clicked(self, _: Gtk.Button):
        self.emit("request_rename", self._title)

    def link_paste_button_clicked(self, _: Gtk.Button):
        self.emit("request_paste", self._title)

    def __init__(self, title: str, url: str):
        super().__init__()
        self._title = title
        markup = f'<a href="{url}">{GLib.markup_escape_text(title)}</a>'
        self._link_label.set_markup(markup)

        _ = self._rename_button.connect("clicked", self.rename_select_button_clicked)
        _ = self._link_paste_button.connect("clicked", self.link_paste_button_clicked)

    def set_button_status(self, enable: bool):
        self._rename_button.set_sensitive(enable)
        self._link_paste_button.set_sensitive(enable)


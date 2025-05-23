import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, GLib # pyright: ignore[reportMissingModuleSource]

@Gtk.Template(filename="ui/linked_item.ui")
class SidebarLinkRow(Gtk.ListBoxRow):
    '''
    Template for entries in the linked pages list.
    '''
    __gtype_name__: str = "SidebarLinkRow"

    _link_label: Gtk.Label = Gtk.Template.Child(name="link_label") # pyright: ignore[reportAny]

    def __init__(self, title: str, url: str):
        super().__init__()
        markup = f'<a href="{url}">{GLib.markup_escape_text(title)}</a>'
        self._link_label.set_markup(markup)

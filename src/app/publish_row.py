# pyright: reportAny=false
import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk # pyright: ignore[reportMissingModuleSource]

from app.databags import STATUS_ICONS, PublishStage, StatusState, StatusVisual

@Gtk.Template(filename="ui/publish_modal_item.ui")
class PublishRow(Gtk.ListBoxRow):
    __gtype_name__: str = "MediaWikiPublishRow"

    _publish_page_label: Gtk.Label = Gtk.Template.Child(name="publish_page_label")
    _publish_status_label: Gtk.Label = Gtk.Template.Child(name="publish_status_label")

    _edit_stack: Gtk.Stack = Gtk.Template.Child(name="edit_stack")
    _edit_status_spinner: Gtk.Spinner = Gtk.Template.Child(name="edit_status_spinner")
    _edit_status_icon: Gtk.Image = Gtk.Template.Child(name="edit_status_icon")

    _move_stack: Gtk.Stack = Gtk.Template.Child(name="move_stack")
    _move_status_spinner: Gtk.Spinner = Gtk.Template.Child(name="move_status_spinner")
    _move_status_icon: Gtk.Image = Gtk.Template.Child(name="move_status_icon")

    def __init__(self, title: str) -> None:
        super().__init__()
        self._publish_page_label.set_label(title)
        self.set_status(PublishStage.EDIT, STATUS_ICONS[StatusState.SCHEDULED])
        self.set_status(PublishStage.MOVE, STATUS_ICONS[StatusState.SCHEDULED])

    def set_status(
        self,
        stage: PublishStage,
        visual: StatusVisual
    ) -> None:
        self._publish_status_label.set_label(visual.label)

        if stage == PublishStage.DONE:
            return
    
        match stage:
            case PublishStage.EDIT:
                stack = self._edit_stack
                spinner = self._edit_status_spinner
                icon = self._edit_status_icon
            case PublishStage.MOVE:
                stack = self._move_stack
                spinner = self._move_status_spinner
                icon = self._move_status_icon
            #case _:
            #    raise ValueError("Unknown stage; expected 'edit' or 'move'.")

        tooltip = visual.tooltip
        spinner.set_tooltip_text(tooltip)
        icon.set_tooltip_text(tooltip)

        if visual.icon is None: # assume that no icon means we want spinner
            spinner.start()
            stack.set_visible_child(spinner)
        else:
            spinner.stop()
            icon.set_from_icon_name(visual.icon)
            stack.set_visible_child(icon)

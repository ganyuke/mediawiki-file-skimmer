# pyright: reportAny=false
import gi
gi.require_version('Gtk', '4.0')
from gi.repository import GObject, Gtk # pyright: ignore[reportMissingModuleSource]
from diff_match_patch import diff_match_patch

@Gtk.Template(filename="ui/submission_modal.ui")
class StagingDialog(Gtk.Window):
    '''
    Template for dialog shown when staging changes.
    '''
    __gtype_name__: str = "staging-dialog"
    __gsignals__: dict[str, tuple[int, None | type, tuple[type, ...]]] = {
        "confirmed": (GObject.SignalFlags.RUN_FIRST, None, ())
    }

    _wikitext_buffer: Gtk.TextBuffer = Gtk.Template.Child(name="wikitext-text-view-buffer")
    _rename_label: Gtk.Label = Gtk.Template.Child(name="rename-review-label")
    _cancel_btn: Gtk.Button = Gtk.Template.Child(name="cancel-submit-button")
    _confirm_btn: Gtk.Button = Gtk.Template.Child(name="confirm-submit-button")
    _rename_panel: Gtk.Box = Gtk.Template.Child(name="rename-review-panel")

    def render_diff(self, original_text: str, modified_text: str):
        dmp = diff_match_patch()
        diffs = dmp.diff_main(original_text, modified_text)
        dmp.diff_cleanupSemantic(diffs)

        buffer = self._wikitext_buffer
        tag_insert = buffer.create_tag("insert", background="lightgreen")
        tag_delete = buffer.create_tag("delete", background="pink")

        for op, data in diffs:
            start = buffer.get_end_iter()
            buffer.insert(start, data)
            start = buffer.get_iter_at_offset(buffer.get_char_count() - len(data))
            end = buffer.get_end_iter()
            if op == dmp.DIFF_INSERT:
                buffer.apply_tag(tag_insert, start, end)
            elif op == dmp.DIFF_DELETE:
                buffer.apply_tag(tag_delete, start, end)

    def __init__(self, parent: Gtk.Window, original_title: str, original_text: str, modified_title: str | None, modified_text: str | None):
        super().__init__()
        self.set_transient_for(parent)

        if (modified_title is not None):
            self._rename_panel.show()
            self._rename_label.set_text(f'{original_title} -> {modified_title}')
        else:
            self._rename_panel.hide()
            
        if (modified_text is not None):
            self.render_diff(original_text, modified_text)
        else:
            iter = self._wikitext_buffer.get_start_iter()
            self._wikitext_buffer.insert(iter, text=original_text)

        _ = self._cancel_btn.connect('clicked', self.on_cancel)
        _ = self._confirm_btn.connect('clicked', self.on_confirm)

    def on_cancel(self, _button: Gtk.Button) -> None:
        self.destroy()

    def on_confirm(self, _button: Gtk.Button) -> None:
        self.emit("confirmed")
        self.destroy()
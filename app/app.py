import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, Gio # pyright: ignore[reportMissingModuleSource]

import asyncio
import threading
from typing import override
from config import AppConfig
from api.http_client import MediaWikiClient
from app.databags import AppDeps
from app.window import MediaWikiViewerWindow

class MediaWikiViewerApp(Gtk.Application):
    '''
    Overarching GTK application runtime handler.
    '''
    _window: MediaWikiViewerWindow
    _deps: AppDeps

    def __init__(self):
        super().__init__(application_id="com.example.MediaWikiViewer",
                         flags=Gio.ApplicationFlags.FLAGS_NONE)
        appConfig = AppConfig()
        client = MediaWikiClient(appConfig.get_api_url())
        self._deps = AppDeps(appConfig, client, self._start_event_loop())

    def _start_event_loop(self):
        def async_thread():
            async_loop.run_forever()

        async_loop = asyncio.new_event_loop()
        threading.Thread(target=async_thread, daemon=True).start()
        return async_loop

    @override
    def do_activate(self):
        if not hasattr(self, "_window"):
            self._window = MediaWikiViewerWindow(application=self, deps=self._deps)
        self._window.present()

    @override
    def do_shutdown(self) -> None:
        def close_client():
            _ = self._deps.event_loop.create_task(self._deps.http_client.close())

        _ = self._deps.event_loop.call_soon_threadsafe(close_client)
        Gio.Application.do_shutdown(self)
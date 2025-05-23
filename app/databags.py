import asyncio
from dataclasses import dataclass
from api.http_client import MediaWikiClient
from config import AppConfig

@dataclass
class AppDeps:
    app_config: AppConfig
    http_client: MediaWikiClient
    event_loop: asyncio.AbstractEventLoop
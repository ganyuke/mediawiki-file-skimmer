from httpx import HTTPStatusError
from pydantic import ValidationError

from api.http_client import MediaWikiClient
from api.databags import BatchResult, Cont, DataPage, MediaWikiResponse, Page

PARAMS = {
	"action": "query",
	"format": "json",
	# "prop": "revisions|imageinfo|fileusage",
    "prop": "revisions|imageinfo",
	"generator": "categorymembers",
	"formatversion": "2",
	"rvprop": "content",
	"rvslots": "main",
	"iiprop": "url",
	"iilimit": "1",
	# "funamespace": "0",
	# "fulimit": "10",
	"gcmtitle": "Category:Example",
	"gcmprop": "title",
	"gcmtype": "file",
	"gcmlimit": "10",
	"gcmsort": "sortkey",
	"gcmdir": "ascending"
}

def log_to_file(entry: str):
    with open("app.log", "a") as f:
        _ = f.write(entry)

class FileUsageBatcher:
    _http_client: MediaWikiClient
    _conts: dict[str, Cont | None] = {}
    _complete: set[str] = set()

    def __init__(self, http_client: MediaWikiClient):
        self._http_client = http_client

    def can_continue(self, title: str):
        if (title in self._conts):
            return self._conts.get(title) is not None
        else:
            return True # for cold-start batches

    async def fetch_usage(self, title: str, limit: int = 50) -> BatchResult[str] | None:
        if (title in self._complete):
            return None

        params = {
            "action": "query",
            "format": "json",
            "prop": "fileusage",
            "formatversion": "2",
            "titles": title,
            "funamespace": "0",
            "fulimit": str(limit),
        }

        cont = self._conts.pop(title, None)
        if (cont is not None):
            contParams = cont.model_dump(exclude_none=True, by_alias=True)
            params.update(contParams)

        linked: set[str] = set()
        resp = await self._http_client.get(params=params)
        
        try:
            _ = resp.raise_for_status()
        except HTTPStatusError as _e:
            log_str = f"GCM HTTP error [{resp.status_code}] for {params}: {resp.text}\n"
            log_to_file(log_str)
            raise RuntimeError(log_str)

        try:
            mw_resp = MediaWikiResponse.model_validate_json(resp.text)
            batch_complete = mw_resp.batchcomplete is True
            cont = mw_resp.cont
            self._conts[title] = cont

            for page in mw_resp.query.pages:
                fusage = page.fileusage
                if (fusage is not None):
                    for usage in fusage:
                        linked.add(usage.title)
                if (batch_complete):
                    self._complete.add(page.title)

            title_list = list(linked)
            result: BatchResult[str] = BatchResult(pages=title_list, complete=batch_complete)
            return result
        except ValidationError as _e:
            log_str = f"Response validation failed for params {params}\nJSON: {resp.text}"
            log_to_file(log_str)
            raise RuntimeError(log_str)        

class CategoryBatcher:
    # for avoiding infinite loops
    _batch_walks: int = 0
    _max_batch_walks: int = 10
    _cont: Cont | None = None
    _http_client: MediaWikiClient
    _base_params: dict[str, str]

    def __init__(self, http_client: MediaWikiClient, category: str):
        self._http_client = http_client
        params: dict[str, str] = PARAMS.copy()
        params["gcmtitle"] = category
        self._base_params = params

    def can_continue(self):
        return self._cont is not None

    async def fetch_batch(self) -> BatchResult[DataPage]:
        batch_complete = False
        batch_dict: dict[str, DataPage] = {}

        while (not batch_complete and self._batch_walks < self._max_batch_walks):
            self._batch_walks += 1
            result: BatchResult[DataPage] = await self.fetch_gcm()
            batch_complete = result.complete

            for page in result.pages:
                existing_page = batch_dict.get(page.title)
                if (existing_page is None):
                    batch_dict[page.title] = page
                else:
                    existing_page.merge(page)

        if (self._batch_walks >= self._max_batch_walks):
            log_str = "Hit batch limit. Aborting walk."
            print(log_str)
            log_to_file(log_str)
            self._batch_walks = 0

        batch_list = list(batch_dict.values())
        batch_result: BatchResult[DataPage] = BatchResult(
            pages=batch_list,
            complete=batch_complete
        )
        return batch_result

    async def fetch_gcm(self) -> BatchResult[DataPage]:
        params: dict[str, str] = self._base_params.copy()
        cont = self._cont
        if (cont is not None):
            contParams = cont.model_dump(exclude_none=True, by_alias=True)
            params.update(contParams)

        resp = await self._http_client.get(params=params)
        
        try:
            _ = resp.raise_for_status()
        except HTTPStatusError as _e:
            log_str = f"GCM HTTP error [{resp.status_code}] for {params}: {resp.text}\n"
            log_to_file(log_str)
            raise RuntimeError(log_str)

        try:
            mw_resp = MediaWikiResponse.model_validate_json(resp.text)
            self._cont = None
            return self.parse_gcm(mw_resp)
        except ValidationError as _e:
            log_str = f"Response validation failed for params {params}\nJSON: {resp.text}"
            log_to_file(log_str)
            raise RuntimeError(log_str)

    def parse_gcm(self, json: MediaWikiResponse) -> BatchResult[DataPage]:
        batch_complete = json.batchcomplete is not None
        pages: list[DataPage] = []
        self._cont = json.cont

        for page in json.query.pages:
            parsed_data = self.parse_page(page)
            pages.append(parsed_data)

        result: BatchResult[DataPage] = BatchResult(
            pages=pages,
            complete=batch_complete
        )
        return result

    def parse_page(self, page: Page) -> DataPage:
        title: str = page.title
        wikitext: str = ""
        image_path: str = ""

        revs = page.revisions
        if (revs is not None):
            rev0 = revs[0]
            main = rev0.slots.get("main")
            if (main is not None):
                wikitext = main.content

        imageinfo = page.imageinfo
        if (imageinfo is not None):
            imageinfo0 = imageinfo[0]
            image_path = imageinfo0.url
        
        return DataPage(
            title,
            wikitext = wikitext,
            image_path = image_path,
        )

class MediaWikiDataService:
    pages: dict[str, DataPage] = {}
    _cat: CategoryBatcher
    _fusage: FileUsageBatcher

    def __init__(self, http_client: MediaWikiClient, category: str):
        self._cat = CategoryBatcher(http_client, category)
        self._fusage = FileUsageBatcher(http_client)

    def _merge_pages(self, pages: list[DataPage]) -> list[DataPage]:
        compiled_batch: list[DataPage] = []
        for page in pages:
            existing_page = self.pages.get(page.title)
            if (existing_page is None):
                self.pages[page.title] = page
                existing_page = page
            else:
                existing_page.merge(page)
            compiled_batch.append(existing_page)

        return compiled_batch

    async def batch_category(self) -> BatchResult[DataPage]:
        """grab the next chunk of files from GCM"""
        result = await self._cat.fetch_batch()

        result: BatchResult[DataPage] = BatchResult(
            pages=self._merge_pages(result.pages),
            complete=result.complete
        )
        return result

    async def batch_file_usage(self, title: str, limit: int = 50) -> BatchResult[str] | None:
        """hydrate / extend linked_pages for one file"""
        result = await self._fusage.fetch_usage(title, limit)
        if result is None:
            return None

        page = self.pages.get(title)
        if (page is None):
            log_str = f"Attempted to update fileusage of unindexed title `{title}`."
            log_to_file(log_str)
            raise RuntimeError(log_str)
        
        page.linked_pages.update(result.pages)
        return result

    def get_page(self, title: str) -> DataPage | None:
        """read-only access for the UI"""
        return self.pages.get(title)

    def can_continue_cat(self):
        return self._cat.can_continue()
    
    def can_continue_fu(self, title: str):
        return self._fusage.can_continue(title)
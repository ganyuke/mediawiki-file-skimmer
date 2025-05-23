import json
import httpx
from pydantic.dataclasses import dataclass
from pydantic import Field, ValidationError

from api.http_client import MediaWikiClient
from api.databags import Cont, FileUsage, MediaWikiResponse, Page

PARAMS = {
	"action": "query",
	"format": "json",
	"prop": "revisions|imageinfo|fileusage",
	"generator": "categorymembers",
	"formatversion": "2",
	"rvprop": "content",
	"rvslots": "main",
	"iiprop": "url",
	"iilimit": "1",
	"funamespace": "0",
	"fulimit": "10",
	"gcmtitle": "Category:Example",
	"gcmprop": "title",
	"gcmtype": "file",
	"gcmlimit": "10",
	"gcmsort": "sortkey",
	"gcmdir": "ascending"
}

@dataclass
class DataPage:
    title: str
    wikitext: str
    image_path: str
    linked_pages: set[str] = Field(default_factory=set)

    def merge(self, other: "DataPage"):
        if (self.title == ""):
            self.title = other.title
        if (self.wikitext == ""):
            self.wikitext = other.wikitext
        if (self.image_path == ""):
            self.image_path = other.image_path
        self.linked_pages.update(other.linked_pages)

class CategoryBatcher:
    pages: dict[str, DataPage] = {}
    _batch: dict[str, DataPage] = {}
    _base_url: str
    _cont: Cont | None = None
    _batchComplete: bool = False
    _baseParams: dict[str, str]
    # for avoiding infinite loops
    _batchWalks: int = 0
    _maxBatchWalks: int = 10
    _http_client: MediaWikiClient

    def __init__(self, base_url: str, category: str, client: MediaWikiClient) -> None:
        self._base_url = base_url
        params: dict[str, str] = PARAMS.copy()
        params["gcmtitle"] = category
        self._baseParams = params
        self._http_client = client

    def isBatchComplete(self) -> bool:
        return self._batchComplete

    def canContinue(self) -> bool:
        return self._cont is not None

    async def fetch_batch(self):
        batchComplete = False
        batchList: list[DataPage] = []

        while (not batchComplete and self._batchWalks < self._maxBatchWalks):
            self._batchWalks += 1
            batchComplete = await self.fetch_gcm()

        if (self._batchWalks >= self._maxBatchWalks):
            print("WARNING: HIT BATCH WALK LIMIT")
            self._batchWalks = 0

        for page in self._batch.values():
            existingPage = self.pages.get(page.title)
            if (existingPage is None):
                self.pages[page.title] = page
            else:
                existingPage.merge(page)
            batchList.append(page)

        self._batch.clear()
        return list(batchList)

    async def fetch_gcm(self) -> bool:
        params: dict[str, str] = self._baseParams.copy()

        if (self._cont is not None):
            contParams = self._cont.model_dump(exclude_none=True, by_alias=True)
            params.update(contParams)

        #with open('examples/api_calls.txt', 'a') as f:
        #    _ = f.write(str(httpx.URL(self._base_url, params=params))+"\n")

        resp = await self._http_client.get(url=self._base_url, params=params)
        if resp.status_code == 200:
            try:
                respJson: MediaWikiResponse = MediaWikiResponse.model_validate(resp.json())
                return self.parse_gcm(respJson)
            except (ValidationError) as e:
                #with open('examples/error.json', 'wb') as f:
                #    _ = f.write(resp.read())
                return True
            except (json.JSONDecodeError, TypeError, ValueError) as e:
                print("ERROR UNMARSHALLING JSON", self._cont)
                print(e)
        
        return True

    def parse_gcm(self, json: MediaWikiResponse) -> bool:
        batchComplete = json.batchcomplete is not None
        self._cont = json.cont

        for page in json.query.pages:
            parsedData = self.parse_page(page)
            existingData = self._batch.get(parsedData.title)
            if (existingData is None):
                self._batch[parsedData.title] = parsedData
            else:
                # DataPage was passed by reference
                # no need to re-set here
                existingData.merge(parsedData)
        
        self._batchComplete = batchComplete
        return batchComplete

    def parse_page(self, page: Page) -> DataPage:
        title: str = page.title
        wikitext: str = ""
        image_path: str = ""
        linked_pages: set[str] = set()

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
        
        fileusage: list[FileUsage] | None = page.fileusage
        if (fileusage is not None):
            for usage in fileusage:
                linked_pages.add(usage.title)

        return DataPage(
            title,
            wikitext = wikitext,
            image_path = image_path,
            linked_pages = linked_pages
        )
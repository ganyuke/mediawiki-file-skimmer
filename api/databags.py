from pydantic import BaseModel, Field

# ------------- #
# BATCH FETCHER #
# ------------- #
class Slot(BaseModel):
    contentmodel: str
    contentformat: str
    content: str

class Revision(BaseModel):
    slots: dict[str, Slot]

class ImageInfo(BaseModel):
    url: str
    descriptionurl: str
    descriptionshorturl: str

class FileUsage(BaseModel):
    pageid: int
    ns: int
    title: str
    redirect: bool

class Page(BaseModel):
    pageid: int
    ns: int
    title: str
    revisions: list[Revision] | None = None
    imageinfo: list[ImageInfo] | None = None
    fileusage: list[FileUsage] | None = None

class Query(BaseModel):
    pages: list[Page]

class Cont(BaseModel):
    cont: str = Field(alias='continue')
    fucontinue: str | None = None
    gcmcontinue: str | None = None
    iucontinue: str | None = None

class MediaWikiResponse(BaseModel):
    batchcomplete: bool | None = None
    query: Query
    cont: Cont | None = Field(alias='continue', default=None)

# ---------------- #
# CATEGORY FETCHER #
# ---------------- #

class CategoryInfo(BaseModel):
    size: int
    pages: int
    files: int
    subcats: int

class CategoryPage(BaseModel):
    pageid: int
    ns: int
    title: str
    categoryinfo: CategoryInfo

class PageNormalize(BaseModel):
    from_: str = Field(alias="from")
    to: str

class CategoryQuery(BaseModel):
    normalized: dict[int, PageNormalize] | None = None
    pages: dict[int, CategoryPage]

class CategoryResp(BaseModel):
    # batch_complete: str
    query: CategoryQuery

# ------------- #
# LOGIN FETCHER #
# ------------- #
class TokenQuery(BaseModel):
    tokens: dict[str, str]

class TokenResponse(BaseModel):
    batchcomplete: str
    query: TokenQuery

#action=query&meta=tokens&format=json
class CsrfToken(BaseModel):
    csrftoken: str

class CsrfTokenInfo(BaseModel):
    tokens: CsrfToken

class CsrfTokenResponse(BaseModel):
    query: CsrfTokenInfo

class LoginInfo(BaseModel):
    lguserid: int
    result: str
    lgusername: str

class LoginResponse(BaseModel):
    login: LoginInfo
#{'login': {'result': 'Aborted', 'reason': 'Cannot log in when using MediaWiki\\Session\\BotPasswordSessionProvider sessions.'}}

# ----------------- #
# USER INFO FETCHER #
# ----------------- #
class UserInfo(BaseModel):
    id: int
    name: str

class UserInfoQuery(BaseModel):
    userinfo: UserInfo

class UserInfoResponse(BaseModel):
    query: UserInfoQuery

#https://en.wikipedia.org/w/api.php?action=login&format=json
#https://en.wikipedia.org/w/api.php?action=query&format=json&meta=tokens&type=login
import httpx
from pydantic import ValidationError
from api.databags import CategoryResp, CsrfTokenResponse, EditResponse, ErrorResponse, LoginResponse, MoveResponse, TokenResponse, UserInfo, UserInfoResponse
from logger import log_to_file
from version import __user_agent__

class MediaWikiClient:
    _api_url: str
    client: httpx.AsyncClient
    _user_info: UserInfo | None = None

    HEADERS: dict[str, str] = {
        "User-Agent": __user_agent__
    }

    CSRF_TOKEN_PARAM: dict[str, str] = {
        "action":"query",
        "meta":"tokens",
        "format":"json"
    }

    LOGIN_TOKEN_PARAM: dict[str, str] = {
        "action": "query",
        "format": "json",
        "meta": "tokens",
        "type": "login"
    }

    LOGIN_PARAM: dict[str, str] = {
        "action": "login",
        "format": "json",
    }

    _debug_mode: bool = False
    _debug_prefix: str = ""

    def __init__(self, api_url: str, debug_mode: bool = False) -> None:
        self._api_url = api_url
        self.client = httpx.AsyncClient(base_url=api_url, headers=self.HEADERS)
        self._debug_mode = debug_mode

    async def get_csrf_token(self) -> str | None:

        resp = await self.get(params=self.CSRF_TOKEN_PARAM)
        try:
            csrf_resp = CsrfTokenResponse.model_validate(resp.json())
            csrftoken = csrf_resp.query.tokens.csrftoken
            return csrftoken
        except (ValidationError):
            return None

    async def login(self, username: str, password: str) -> UserInfo | None:
        try:
            resp = await self.get(params=self.LOGIN_TOKEN_PARAM)
            _ = resp.raise_for_status()

            tokenJson = TokenResponse.model_validate(resp.json())
            loginToken = tokenJson.query.tokens.get("logintoken")

            if (loginToken is None):
                return None

            payload = {
                    "lgname": username,           
                    "lgpassword": password,
                    "lgtoken": loginToken
            }

            payload.update(self.LOGIN_PARAM)

            resp = await self.post(data=payload)
            _ = resp.raise_for_status()
            
            try:        
                login_resp = LoginResponse.model_validate(resp.json())
                login_info = login_resp.login
                if (login_info.result != "Success"):
                    self._user_info = None
                    return None

                user_info = UserInfo(id=login_info.lguserid, name=login_info.lgusername)
                self._user_info = user_info
                # debug mode
                if (self._debug_mode):
                    self._debug_prefix = f"User:{user_info.name}"
                return user_info
            except (ValidationError) as e:
                print(e)
                self._user_info = None
                return None
        except (httpx.HTTPError):
            self._user_info = None
            return None

    async def logout(self) -> bool:
        csrftoken = await self.get_csrf_token()
        if (csrftoken is None):
            log_str = "Failed to get CSRF token during logout."
            log_to_file(log_str)
            print(log_str)
            return False
            #raise RuntimeError()

        payload = {
            "action": "logout",
            "token": csrftoken,
            "format": "json"
        }

        try:
            resp = await self.post(data=payload) # response is probably going to be '{}'
            _ = resp.raise_for_status()
            self._user_info = None # eh, I'm sure they're logged out, right?
            return True
        except (httpx.HTTPError):
            log_str = f"Failed to logout."
            log_to_file(log_str)
            print(log_str)
            return False

    async def get_user_data(self) -> UserInfo | None:
        resp = await self.get({
            "action": "query",
            "meta": "userinfo",
            "format": "json"
        })
        try:
            user_resp = UserInfoResponse.model_validate(resp.json())
            user_info = user_resp.query.userinfo
            if (user_info.id != 0): # user id 0 is an anon (IP)
                return user_info
        except (ValidationError):
            pass

        return None 

    async def check_category_valid(self, category: str) -> bool:
        resp = await self.get({
            "action": "query",
            "titles": category,
            "prop": "categoryinfo",
            "format": "json"
        })
        try:
            cat_resp = CategoryResp.model_validate(resp.json())
            cat_page = next(iter(cat_resp.query.pages.values()))
            if (cat_page.categoryinfo.files > 0):
                return True
        except (ValidationError):
            pass
        return False

    async def publish_rename(self, title: str, new_title: str, reason: str) -> bool:
        if (not self.is_logged_in()):
            raise RuntimeError("Tried to pagemove while not logged in!")

        token= await self.get_csrf_token()
        if (token is None):
            raise RuntimeError("Failed to get CSRF token for pagemove!")

        move_param = {
            "action": "move",
            "from":  self._debug_prefix + title,
            "to": self._debug_prefix + new_title,
            "reason": reason,
            "movetalk": True,
            "movesubpages": True,
            "noredirect": False,
            "token": token,
            "format": "json",
        }

        try:
            resp = await self.client.post(url=self._api_url, data=move_param)
            _ = resp.raise_for_status()
            data = resp.text
            try:
                _result = MoveResponse.model_validate_json(data)
                return True
            except ValidationError:
                try:
                    _error = ErrorResponse.model_validate(data)
                    return False
                except ValidationError:
                    return False
        except (httpx.HTTPError):
            log_str = f"Failed to move page."
            log_to_file(log_str)
            print(log_str)

        return False

    async def publish_edit(self, title: str, new_text: str, summary: str) -> bool:
        if (not self.is_logged_in()):
            raise RuntimeError("Tried to edit while not logged in!")

        token= await self.get_csrf_token()
        if (token is None):
            raise RuntimeError("Failed to get CSRF token for edit!")

        edit_param = {
            "action": "edit",
            "title": self._debug_prefix + title,
            "text": new_text,
            "summary": summary,
            "minor": True,
            "bot": True,
            "token": token,
            "format": "json",
        }

        try:
            resp = await self.client.post(url=self._api_url, data=edit_param)
            _ = resp.raise_for_status()
            data = resp.text
            try:
                _result = EditResponse.model_validate_json(data)
                return True
            except ValidationError:
                try:
                    _error = ErrorResponse.model_validate(data)
                    return False
                except ValidationError:
                    return False
        except (httpx.HTTPError):
            log_str = f"Failed to POST edit."
            log_to_file(log_str)
            print(log_str)

        return False

    async def get(self, params: dict[str, str] | None, override_url: str | None = None) -> httpx.Response:
        url = override_url or self._api_url

        with open('examples/api_calls_2.txt', 'a') as f:
           _ = f.write(str(httpx.URL(url, params=params))+"\n")

        return await self.client.get(url, params=params)

    async def post(self, data: dict[str, str], override_url: str | None = None) -> httpx.Response:
        url = override_url or self._api_url
        return await self.client.post(url, data=data)

    async def close(self) -> None:
        await self.client.aclose()

    def is_logged_in(self) -> bool:
        return self._user_info is not None
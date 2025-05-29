import httpx
from pydantic import ValidationError
from api.databags import CategoryResp, CsrfTokenResponse, LoginResponse, TokenResponse, UserInfo, UserInfoResponse
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

    def __init__(self, api_url: str) -> None:
        self._api_url = api_url
        self.client = httpx.AsyncClient(base_url=api_url, headers=self.HEADERS)

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

        resp = await self.post(data=payload) # response is probably going to be '{}'
        try:
            _ = resp.raise_for_status()
            self._user_info = None # eh, I'm sure they're logged out, right?
            return True
        except (httpx.HTTPError):
            log_str = f"Failed to logout with code {resp.status_code}."
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
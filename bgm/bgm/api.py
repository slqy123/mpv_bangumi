import os
import json
import aiohttp
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from bgm import logger
from bgm import DATA_PATH

class API:
    API_BASE=""
    def __init__(self) -> None:
        self.headers = {}
        self.session = None
        self._include_status_code = False

    async def __aenter__(self):
        await self.init_session()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()


    async def init_session(self):
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession(headers=self.headers)
        

    async def close(self):
        if self.session and not self.session.closed:
            await self.session.close()

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((aiohttp.ClientError, aiohttp.ClientResponseError)),
        reraise=True
    )
    async def _request(self, method: str, url: str, **kwargs) -> dict:
        if self.session is None or self.session.closed:
            raise RuntimeError("Session is not initialized. Please use 'async with' or call 'await api.init_session()'.")

        async with self.session.request(method, url, **kwargs) as res:
            if res.status >= 500 or res.status == 429:
                res.raise_for_status()

            try:
                res_json = await res.json()
            except (aiohttp.ContentTypeError, json.JSONDecodeError):
                text = await res.text()
                res_json = json.loads(text or "{}")

            if self._include_status_code:
                res_json["status_code"] = res.status
            return res_json

    async def get(self, uri: str, params: dict | None = None):
        return await self._request("GET", self.API_BASE + uri, params=params or {})

    async def post(self, uri: str, data: dict | None = None):
        return await self._request("POST", self.API_BASE + uri, json=data or {})

    async def put(self, uri: str, data: dict | None = None):
        return await self._request("PUT", self.API_BASE + uri, json=data or {})


class BangumiAPI(API):
    API_BASE = "https://api.bgm.tv"
    ACCESS_TOKEN = os.environ["BGM_ACCESS_TOKEN"]
    default_headers = {
        "accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": "mpv_bangumi/private",
    }

    def __init__(self):
        super().__init__()
        self._include_status_code = True
        self.headers = self.default_headers | {
            "Authorization": f"Bearer {self.ACCESS_TOKEN}"
        }
        self.username = None

    async def init_session(self):
        await super().init_session()
        if not self.username:
            await self._init_username()

    async def _init_username(self):
        username_file = DATA_PATH / "username.json"
        if username_file.exists():
            with open(username_file, "r", encoding="utf-8") as f:
                username_data = json.load(f)
        else:
            username_data = {}

        if self.ACCESS_TOKEN in username_data:
            self.username = username_data[self.ACCESS_TOKEN]
        else:
            self.username = await self.get_username()
            if self.username is None:
                logger.error("Failed to get username, please check your access token.")
                exit(-1)
            username_data[self.ACCESS_TOKEN] = self.username
            with open(username_file, "w", encoding="utf-8") as f:
                json.dump(username_data, f)
        assert isinstance(self.username, str), "Username must be a string"

    async def get_subject(self, item_id: int):
        return await self.get(f"/v0/subjects/{item_id}")

    async def search(self, keyword: str):
        url = f"https://api.bgm.tv/search/subject/{keyword}"
        return await self._request("GET", url, params={"type": 4})

    async def get_username(self):
        res = await self.get("/v0/me")
        return res.get("username", None)

    async def get_user_collection(self, subject_id: int):
        return await self.get(f"/v0/users/{self.username}/collections/{subject_id}")

    async def update_user_collection(
        self, subject_id: int, status: int = 3, private: bool = False
    ):
        """status 1: 想看, 2: 看过, 3: 在看, 4: 搁置, 5: 抛弃"""
        return await self.post(
            f"/v0/users/-/collections/{subject_id}",
            data={"type": status, "private": private},
        )

    async def get_user_episodes(self, subject_id: int):
        return await self.get(
            f"/v0/users/-/collections/{subject_id}/episodes",
            {"offset": 0, "limit": 1000, "episode_type": 0},
        )

    async def get_episode_status(self, episode_id: int):
        return await self.get(f"/v0/users/-/collections/-/episodes/{episode_id}")

    async def update_episode_status(self, episode_id: int, status: int = 2):
        """status 0: 未收藏, 1: 想看, 2: 看过, 3: 抛弃"""
        return await self.put(
            f"/v0/users/-/collections/-/episodes/{episode_id}",
            data={"type": status},
        )

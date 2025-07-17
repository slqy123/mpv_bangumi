import os
import requests
import json
from bgm import logger
from bgm import DATA_PATH


class BangumiAPI:
    API_URL = "https://api.bgm.tv"
    ACCESS_TOKEN = os.environ["BGM_ACCESS_TOKEN"]
    default_headers = {
        "accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": "mpv_bangumi/private",
    }

    def __init__(self):
        self.headers = self.default_headers | {
            "Authorization": f"Bearer {self.ACCESS_TOKEN}"
        }

        # get username
        username_file = DATA_PATH / "username.json"
        if username_file.exists():
            with open(username_file, "r", encoding="utf-8") as f:
                username_data = json.load(f)
        else:
            username_data = {}

        if self.ACCESS_TOKEN in username_data:
            self.username = username_data[self.ACCESS_TOKEN]
        else:
            self.username = self.get_username()
            if self.username is None:
                logger.error("Failed to get username, please check your access token.")
                exit(-1)
            username_data[self.ACCESS_TOKEN] = self.username
            with open(username_file, "w", encoding="utf-8") as f:
                json.dump(username_data, f)
        assert isinstance(self.username, str), "Username must be a string"

    def get(self, uri: str, params: dict | None = None):
        res = requests.get(
            self.API_URL + uri,
            headers=self.headers,
            params=params or {},
        )
        res_json = json.loads(res.content or "{}")
        res_json["status_code"] = res.status_code
        return res_json

    def post(self, uri: str, data: dict | None = None):
        res = requests.post(
            self.API_URL + uri,
            headers=self.headers,
            json=data or {},
        )
        res_json = json.loads(res.content or "{}")
        res_json["status_code"] = res.status_code
        return res_json

    def put(self, uri: str, data: dict | None = None):
        res = requests.put(
            self.API_URL + uri,
            headers=self.headers,
            json=data or {},
        )
        res_json = json.loads(res.content or "{}")
        res_json["status_code"] = res.status_code
        return res_json

    def get_subject(self, item_id: int):
        res = self.get(f"/v0/subjects/{item_id}")
        return res

    def search(self, keyword: str):
        res = requests.get(
            f"https://api.bgm.tv/search/subject/{keyword}",
            params={"type": 4},
            headers=self.headers,
        )
        try:
            return res.json()
        except json.JSONDecodeError:
            logger.error("Json Decoding Error for " + res.content.decode())
            exit(-1)

    def get_username(self):
        res = self.get("/v0/me")
        return res.get("username", None)

    def get_user_collection(self, subject_id: int):
        res = self.get(f"/v0/users/{self.username}/collections/{subject_id}")
        return res

    def update_user_collection(
        self, subject_id: int, status: int = 3, private: bool = False
    ):
        """
        status 1: 想看, 2: 看过, 3: 在看, 4: 搁置, 5: 抛弃,
        """
        res = self.post(
            f"/v0/users/-/collections/{subject_id}",
            data={"type": status, "private": private},
        )
        return res

    def get_user_episodes(self, subject_id: int):
        res = self.get(
            f"/v0/users/-/collections/{subject_id}/episodes",
            {"offset": 0, "limit": 1000, "episode_type": 0},
        )
        return res

    def get_episode_status(self, episode_id: int):
        res = self.get(f"/v0/users/-/collections/-/episodes/{episode_id}")
        return res

    def update_episode_status(self, episode_id: int, status: int = 2):
        """
        status 0: 未收藏, 1: 想看, 2: 看过, 3: 抛弃,
        """
        res = self.put(
            f"/v0/users/-/collections/-/episodes/{episode_id}",
            data={"type": status},
        )
        return res

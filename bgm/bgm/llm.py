import json
import os
import typing
from pathlib import Path

from openai import AsyncOpenAI

from bgm import logger
from bgm.config import config


SYSTEM_PROMPT = (
    "You are a danmaku (弹幕) translator. Translate Japanese danmaku comments to natural Chinese.\n"
    "Input rows: id|time|text\n"
    "Output rows: id|translation (one per input row, same order)\n"
    "Guidelines:\n"
    "- Preserve the tone: humor, excitement, sarcasm, etc.\n"
    "- Keep internet slang style (www→哈哈哈, 草→草/笑, 88888→88888)\n"
    "- Keep translations concise\n"
    "- If a comment is already in Chinese or is just numbers/symbols, keep it as-is\n"
    "- Do NOT output any other text, markdown, or formatting"
)


class LLMClient:
    def __init__(self):
        self.api_key = os.environ.get("LLM_API_KEY")
        llm_cfg = config.llm
        self.base_url = llm_cfg.base_url if llm_cfg else "https://api.openai.com/v1"
        self.model = llm_cfg.model if llm_cfg else "gpt-4o-mini"
        self.client = AsyncOpenAI(api_key=self.api_key, base_url=self.base_url)

    async def chat_lines(self, system: str, user: str) -> dict[str, str]:
        resp = await self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            extra_body={"thinking": {"type": "disabled"}},
        )
        if usage := resp.usage:
            details = []
            details.append(f"model={self.model}")
            details.append(f"prompt={usage.prompt_tokens}")
            details.append(f"completion={usage.completion_tokens}")
            details.append(f"total={usage.total_tokens}")
            if usage.prompt_tokens_details:
                pd = usage.prompt_tokens_details
                if pd.cached_tokens:
                    details.append(f"cached={pd.cached_tokens}")
            if usage.completion_tokens_details:
                cd = usage.completion_tokens_details
                if cd.reasoning_tokens:
                    details.append(f"reasoning={cd.reasoning_tokens}")
            logger.debug("llm: %s", " | ".join(details))
        content = resp.choices[0].message.content
        if not content:
            return {}

        result: dict[str, str] = {}
        for line in content.strip().split("\n"):
            line = line.strip()
            if not line or "|" not in line:
                continue
            id_str, translation = line.split("|" ,1)
            id_str = id_str.strip()
            if not id_str.isdigit():
                continue
            translation = translation.strip()
            if "|" in translation:
                time, translation_ = translation.split("|", 1)
                if time.replace(".", "").isdigit():
                    translation = translation_
            if translation:
                result[id_str] = translation
        return result


class DanmakuTranslator:
    def __init__(self, data_path: Path, video_id: str):
        self.data_path = data_path
        self.video_id = video_id
        self.cache_path = data_path / f"{video_id}.translation.json"
        self._llm: LLMClient | None = None

    @property
    def llm(self) -> LLMClient:
        if self._llm is None:
            self._llm = LLMClient()
        return self._llm

    async def translate(
        self,
        danmaku: list[dict],
        title: str,
        on_update: typing.Callable[[list[dict], bool], typing.Awaitable[None]],
    ) -> None:
        if not danmaku:
            await on_update(danmaku, True)
            return

        sorted_danmaku = sorted(danmaku, key=lambda d: float(d["p"].split(",")[0]))
        cache = self._load_cache()

        translations: dict[str, str] = cache.get("translations", {}).copy()
        translated_keys = set(translations.keys())

        untranslated = [
            (i, d) for i, d in enumerate(sorted_danmaku)
            if self._comment_key(d) not in translated_keys
        ]

        if not untranslated:
            self._apply_translations(sorted_danmaku, translations)
            await on_update(sorted_danmaku, True)
            return

        logger.info("llm: translating %d untranslated comments", len(untranslated))

        self._apply_translations(sorted_danmaku, translations)
        await on_update(sorted_danmaku, False)

        CHUNK_SIZE = 100
        n_chunks = (len(untranslated) + CHUNK_SIZE - 1) // CHUNK_SIZE

        for ci in range(n_chunks):
            is_last = ci == n_chunks - 1
            start = ci * CHUNK_SIZE
            end = min(start + CHUNK_SIZE, len(untranslated))
            chunk = untranslated[start:end]
            input_lines = "\n".join(
                f"{i}|{d['p'].split(',')[0]}|{d['m']}"
                for i, d in chunk
            )

            logger.info("llm: chunk %d/%d (%d–%d)",
                        ci + 1, n_chunks, start, end - 1)

            try:
                result = await self.llm.chat_lines(SYSTEM_PROMPT, input_lines)
            except Exception as e:
                logger.error("llm: chunk %d/%d failed: %s", ci + 1, n_chunks, e)
                continue

            expected_ids = {str(i) for i, _ in chunk}
            missing = expected_ids - result.keys()
            if missing:
                logger.warning("llm: chunk %d/%d missing %d/%d IDs: %s",
                               ci + 1, n_chunks, len(missing), len(chunk),
                               sorted(missing, key=int)[:10])

            for i, d in chunk:
                key = self._comment_key(d)
                trans = result.get(str(i))
                if trans is not None:
                    translations[key] = trans

            self._apply_translations(sorted_danmaku, translations)
            self._write_cache(translations)
            logger.debug("llm: progress %d/%d", len(translations), len(sorted_danmaku))

            if not is_last:
                await on_update(sorted_danmaku, False)

        await on_update(sorted_danmaku, True)

    @staticmethod
    def _comment_key(d: dict) -> str:
        return f"{d['p'].split(',')[0]}|{d['m']}"

    def _load_cache(self) -> dict:
        if not self.cache_path.exists():
            return {}
        try:
            with self.cache_path.open("r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            logger.warning("llm: failed to load translation cache %s", self.cache_path)
            return {}

    def _write_cache(self, translations: dict[str, str]) -> None:
        self.data_path.mkdir(parents=True, exist_ok=True)
        with self.cache_path.open("w", encoding="utf-8") as f:
            json.dump({"translations": translations}, f, ensure_ascii=False)

    @staticmethod
    def _apply_translations(danmaku: list[dict], translations: dict[str, str]) -> None:
        for d in danmaku:
            key = f"{d['p'].split(',')[0]}|{d['m']}"
            if trans := translations.get(key):
                d["m_original"] = d["m"]
                d["m"] = trans

import json
import os
import typing
from pathlib import Path

from openai import AsyncOpenAI

from bgm import logger
from bgm.config import config

SYSTEM_PROMPT = (
    "You are a danmaku (弹幕) translator. Translate Japanese danmaku comments to natural Chinese.\n"
    "Input sections:\n"
    "#TITLE: the video title, for context only\n"
    "#TERMS: the proper-noun glossary (source|translation) you must follow strictly\n"
    "#DANMAKU: comment rows id|time|text\n"
    "Output sections, in this order:\n"
    "#TERMS: the updated glossary, one row per term: source|translation. Keep every input term "
    "unchanged and append every new proper noun (person, place, organization, item, catchphrase, "
    "etc.) you translated\n"
    "#TRANSLATIONS: one row per input row, in the same order: id|translation\n"
    "Guidelines:\n"
    "- Use one single, consistent translation for each proper noun everywhere\n"
    "- Preserve the tone: humor, excitement, sarcasm, etc.\n"
    "- Keep internet slang style (www→哈哈哈, 草→草/笑, 88888→88888)\n"
    "- Keep translations concise\n"
    "- If a comment is already in Chinese or is just numbers/symbols, keep it as-is\n"
    "- Do NOT output any other text, markdown, or formatting"
)


class LLMResult(typing.NamedTuple):
    translations: dict[str, str]
    terms: dict[str, str]


def _parse_content(content: str) -> LLMResult:
    translations: dict[str, str] = {}
    terms: dict[str, str] = {}
    section: str | None = None
    for line in content.strip().split("\n"):
        line = line.strip()
        if not line:
            continue
        if line.startswith("#"):
            name = line.lstrip("# ").strip()
            upper = name.upper()
            if "TERM" in upper or "GLOSSARY" in upper or "术语" in name:
                section = "terms"
            elif "TRANSLAT" in upper or "DANMAKU" in upper or "翻译" in name:
                section = "translations"
            else:
                section = None
            continue
        if section == "terms":
            if "|" in line:
                src, dst = (part.strip() for part in line.split("|", 1))
                if src and dst and src != dst:
                    terms[src] = dst
            continue
        # translation rows may appear before any recognized section header
        if "|" not in line:
            continue
        id_str, translation = line.split("|", 1)
        id_str = id_str.strip()
        if not id_str.isdigit():
            continue
        translation = translation.strip()
        if "|" in translation:
            time, translation_ = translation.split("|", 1)
            if time.replace(".", "").isdigit():
                translation = translation_
        if translation:
            translations[id_str] = translation
    return LLMResult(translations, terms)


class LLMClient:
    def __init__(self):
        self.api_key = os.environ.get("LLM_API_KEY")
        llm_cfg = config.llm
        self.base_url = llm_cfg.base_url if llm_cfg else "https://api.deepseek.com"
        self.model = llm_cfg.model if llm_cfg else "deepseek-flash"
        self.use_responses_api = llm_cfg.use_responses_api if llm_cfg else False
        self.thinking = llm_cfg.thinking if llm_cfg else True
        self.reasoning_effort = llm_cfg.reasoning_effort if llm_cfg else "low"
        self.client = AsyncOpenAI(api_key=self.api_key, base_url=self.base_url)

    def _log_usage(
        self,
        prompt: int,
        completion: int,
        total: int,
        cached: int | None,
        reasoning: int | None,
    ) -> None:
        details = [
            f"model={self.model}",
            f"prompt={prompt}",
            f"completion={completion}",
            f"total={total}",
        ]
        if cached:
            details.append(f"cached={cached}")
        if reasoning:
            details.append(f"reasoning={reasoning}")
        logger.debug("llm: %s", " | ".join(details))

    def _thinking_kwargs(self) -> dict:
        effort = self.reasoning_effort if self.thinking else "none"
        if self.use_responses_api:
            return {"reasoning": {"effort": effort}}
        kwargs = {
            "extra_body": {
                "thinking": {"type": "enabled" if self.thinking else "disabled"}
            }
        }
        if self.thinking:
            kwargs["reasoning_effort"] = self.reasoning_effort
        return kwargs

    async def chat_lines(self, system: str, user: str) -> LLMResult:
        if self.use_responses_api:
            resp = await self.client.responses.create(
                model=self.model,
                instructions=system,
                input=user,
                **self._thinking_kwargs(),
            )
            if usage := resp.usage:
                self._log_usage(
                    usage.input_tokens,
                    usage.output_tokens,
                    usage.total_tokens,
                    usage.input_tokens_details.cached_tokens
                    if usage.input_tokens_details else None,
                    usage.output_tokens_details.reasoning_tokens
                    if usage.output_tokens_details else None,
                )
            content = resp.output_text
        else:
            resp = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                **self._thinking_kwargs(),
            )
            if usage := resp.usage:
                self._log_usage(
                    usage.prompt_tokens,
                    usage.completion_tokens,
                    usage.total_tokens,
                    usage.prompt_tokens_details.cached_tokens
                    if usage.prompt_tokens_details else None,
                    usage.completion_tokens_details.reasoning_tokens
                    if usage.completion_tokens_details else None,
                )
            content = resp.choices[0].message.content
        if not content:
            return LLMResult({}, {})
        return _parse_content(content)


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
        terms: dict[str, str] = cache.get("terms", {}).copy()
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
                result = await self.llm.chat_lines(
                    SYSTEM_PROMPT, self._build_input(title, terms, input_lines)
                )
            except Exception as e:
                logger.error("llm: chunk %d/%d failed: %s", ci + 1, n_chunks, e)
                continue

            expected_ids = {str(i) for i, _ in chunk}
            missing = expected_ids - result.translations.keys()
            if missing:
                logger.warning("llm: chunk %d/%d missing %d/%d IDs: %s",
                               ci + 1, n_chunks, len(missing), len(chunk),
                               sorted(missing, key=int)[:10])

            for i, d in chunk:
                key = self._comment_key(d)
                trans = result.translations.get(str(i))
                if trans is not None:
                    translations[key] = trans

            new_terms = {src: dst for src, dst in result.terms.items() if src not in terms}
            if new_terms:
                terms.update(new_terms)
                logger.debug("llm: chunk %d/%d learned %d new terms",
                             ci + 1, n_chunks, len(new_terms))

            self._apply_translations(sorted_danmaku, translations)
            self._write_cache(translations, terms)
            logger.debug("llm: progress %d/%d", len(translations), len(sorted_danmaku))

            if not is_last:
                await on_update(sorted_danmaku, False)

        await on_update(sorted_danmaku, True)

    @staticmethod
    def _build_input(title: str, terms: dict[str, str], input_lines: str) -> str:
        parts = []
        if title:
            parts.append(f"#TITLE\n{title}")
        terms_block = "#TERMS"
        if terms:
            terms_block += "\n" + "\n".join(f"{src}|{dst}" for src, dst in terms.items())
        parts.append(terms_block)
        parts.append(f"#DANMAKU\n{input_lines}")
        return "\n".join(parts)

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

    def _write_cache(self, translations: dict[str, str], terms: dict[str, str]) -> None:
        self.data_path.mkdir(parents=True, exist_ok=True)
        with self.cache_path.open("w", encoding="utf-8") as f:
            json.dump({"translations": translations, "terms": terms}, f, ensure_ascii=False)

    @staticmethod
    def _apply_translations(danmaku: list[dict], translations: dict[str, str]) -> None:
        for d in danmaku:
            key = f"{d['p'].split(',')[0]}|{d['m']}"
            if trans := translations.get(key):
                d["m_original"] = d["m"]
                d["m"] = trans

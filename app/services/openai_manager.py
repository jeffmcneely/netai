import logging
import time


logger = logging.getLogger(__name__)


class OpenAIManager:
    def __init__(self, api_key: str, model: str):
        self.api_key = (api_key or "").strip()
        self.model = (model or "gpt-5.2").strip() or "gpt-5.2"

    def optimize_acl(self, current_acl: str) -> str:
        if not self.api_key:
            raise RuntimeError("OPENAI_API_KEY is not configured")

        prompt = (
            "optimize these rules. do not add additional access. merge rules where it will simplify access. "
            "remove any rules that are unreachable. do not change order of rules. "
            "only return optimized rules with no commentary"
        )

        try:
            from openai import OpenAI
        except Exception as exc:  # pragma: no cover
            raise RuntimeError("openai package is not installed") from exc

        start = time.perf_counter()
        print(
            f"[OPENAI DEBUG] optimize start model={self.model} current_acl_chars={len(current_acl)}",
            flush=True,
        )
        logger.debug(
            "OPENAI optimize start model=%s current_acl_chars=%d",
            self.model,
            len(current_acl),
        )
        client = OpenAI(api_key=self.api_key)
        try:
            response = client.responses.create(
                model=self.model,
                input=[
                    {
                        "role": "system",
                        "content": [
                            {
                                "type": "input_text",
                                "text": "You optimize access control rules and return only the final ACL text.",
                            }
                        ],
                    },
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "input_text",
                                "text": f"{prompt}\n\n{current_acl}",
                            }
                        ],
                    },
                ],
            )
        except Exception:
            elapsed_ms = int((time.perf_counter() - start) * 1000)
            print(f"[OPENAI DEBUG] optimize failed after {elapsed_ms}ms", flush=True)
            logger.exception("OPENAI optimize failed after %dms", elapsed_ms)
            raise

        output_text = (response.output_text or "").strip()
        elapsed_ms = int((time.perf_counter() - start) * 1000)
        print(
            f"[OPENAI DEBUG] optimize response model={self.model} elapsed_ms={elapsed_ms} candidate_chars={len(output_text)}",
            flush=True,
        )
        logger.debug(
            "OPENAI optimize response model=%s elapsed_ms=%d candidate_chars=%d",
            self.model,
            elapsed_ms,
            len(output_text),
        )
        if not output_text:
            raise RuntimeError("OpenAI returned an empty response")

        return output_text

    def generate_acl_commands(self, platform_context: str, current_acl: str, candidate_acl: str) -> str:
        if not self.api_key:
            raise RuntimeError("OPENAI_API_KEY is not configured")

        prompt = (
            f"this is a section from a {platform_context} config. add appropriate checkpoint/backup/revert commands at beginning and end if appropriate. "
            "provide commands to change from current acl list to candidate acl list "
            f"current: {current_acl} candidate: {candidate_acl}. "
            "Return the result as Markdown with clear sections and fenced code blocks for commands. "
            "Do not include any non-Markdown wrapper text."
        )

        try:
            from openai import OpenAI
        except Exception as exc:  # pragma: no cover
            raise RuntimeError("openai package is not installed") from exc

        start = time.perf_counter()
        print(
            f"[OPENAI DEBUG] generate-commands start model={self.model} current_acl_chars={len(current_acl)} candidate_acl_chars={len(candidate_acl)}",
            flush=True,
        )
        logger.debug(
            "OPENAI generate-commands start model=%s current_acl_chars=%d candidate_acl_chars=%d",
            self.model,
            len(current_acl),
            len(candidate_acl),
        )

        client = OpenAI(api_key=self.api_key)
        try:
            response = client.responses.create(
                model=self.model,
                input=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "input_text",
                                "text": prompt,
                            }
                        ],
                    },
                ],
            )
        except Exception:
            elapsed_ms = int((time.perf_counter() - start) * 1000)
            print(f"[OPENAI DEBUG] generate-commands failed after {elapsed_ms}ms", flush=True)
            logger.exception("OPENAI generate-commands failed after %dms", elapsed_ms)
            raise

        output_text = (response.output_text or "").strip()
        elapsed_ms = int((time.perf_counter() - start) * 1000)
        print(
            f"[OPENAI DEBUG] generate-commands response model={self.model} elapsed_ms={elapsed_ms} output_chars={len(output_text)}",
            flush=True,
        )
        logger.debug(
            "OPENAI generate-commands response model=%s elapsed_ms=%d output_chars=%d",
            self.model,
            elapsed_ms,
            len(output_text),
        )
        if not output_text:
            raise RuntimeError("OpenAI returned an empty response")

        return output_text

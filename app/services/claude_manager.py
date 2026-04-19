import logging
import time


logger = logging.getLogger(__name__)


CLAUDE_REQUEST_TIMEOUT_SECONDS = 120.0


class ClaudeTimeoutError(RuntimeError):
    pass


def _is_timeout_error(exc: Exception) -> bool:
    if isinstance(exc, TimeoutError):
        return True
    if exc.__class__.__name__ in {"APITimeoutError", "TimeoutException"}:
        return True
    return "timed out" in str(exc).lower()


class ClaudeManager:
    def __init__(self, api_key: str, model: str):
        self.api_key = (api_key or "").strip()
        self.model = (model or "claude-sonnet-4-5").strip() or "claude-sonnet-4-5"

    def optimize_acl(self, current_acl: str) -> str:
        if not self.api_key:
            raise RuntimeError("CLAUDE_API_KEY is not configured")

        prompt = (
            "optimize these rules. do not add additional access. merge rules where it will simplify access. "
            "remove any rules that are unreachable. do not change order of rules. remove rules that are redundant. remove rules that have no effect."
            "only return optimized rules with no commentary"
        )

        try:
            from anthropic import Anthropic
        except Exception as exc:  # pragma: no cover
            raise RuntimeError("anthropic package is not installed") from exc

        start = time.perf_counter()
        print(
            f"[CLAUDE DEBUG] optimize start model={self.model} current_acl_chars={len(current_acl)}",
            flush=True,
        )
        logger.debug(
            "CLAUDE optimize start model=%s current_acl_chars=%d",
            self.model,
            len(current_acl),
        )

        client = Anthropic(api_key=self.api_key, timeout=CLAUDE_REQUEST_TIMEOUT_SECONDS)
        try:
            response = client.messages.create(
                model=self.model,
                max_tokens=8192,
                system="You optimize access control rules and return only the final ACL text.",
                messages=[
                    {
                        "role": "user",
                        "content": f"{prompt}\n\n{current_acl}",
                    }
                ],
            )
        except Exception as exc:
            elapsed_ms = int((time.perf_counter() - start) * 1000)
            print(f"[CLAUDE DEBUG] optimize failed after {elapsed_ms}ms", flush=True)
            logger.exception("CLAUDE optimize failed after %dms", elapsed_ms)
            if _is_timeout_error(exc):
                raise ClaudeTimeoutError(
                    f"Claude request timed out after {int(CLAUDE_REQUEST_TIMEOUT_SECONDS)} seconds. Please retry."
                ) from exc
            raise

        output_text = ""
        for block in (response.content or []):
            if getattr(block, "type", "") == "text":
                output_text += getattr(block, "text", "")
        output_text = output_text.strip()

        elapsed_ms = int((time.perf_counter() - start) * 1000)
        print(
            f"[CLAUDE DEBUG] optimize response model={self.model} elapsed_ms={elapsed_ms} candidate_chars={len(output_text)}",
            flush=True,
        )
        logger.debug(
            "CLAUDE optimize response model=%s elapsed_ms=%d candidate_chars=%d",
            self.model,
            elapsed_ms,
            len(output_text),
        )

        if not output_text:
            raise RuntimeError("Claude returned an empty response")

        return output_text

    def generate_acl_commands(self, platform_context: str, current_acl: str, candidate_acl: str) -> str:
        if not self.api_key:
            raise RuntimeError("CLAUDE_API_KEY is not configured")

        prompt = (
            f"this is a section from a {platform_context} config. add appropriate checkpoint/backup/revert commands at beginning and end if appropriate. "
            "provide commands to change from current acl list to candidate acl list "
            f"current: {current_acl} candidate: {candidate_acl}. "
            "Return the result as Markdown with clear sections and fenced code blocks for commands. "
            "Do not include any non-Markdown wrapper text."
        )

        try:
            from anthropic import Anthropic
        except Exception as exc:  # pragma: no cover
            raise RuntimeError("anthropic package is not installed") from exc

        start = time.perf_counter()
        print(
            f"[CLAUDE DEBUG] generate-commands start model={self.model} current_acl_chars={len(current_acl)} candidate_acl_chars={len(candidate_acl)}",
            flush=True,
        )
        logger.debug(
            "CLAUDE generate-commands start model=%s current_acl_chars=%d candidate_acl_chars=%d",
            self.model,
            len(current_acl),
            len(candidate_acl),
        )

        client = Anthropic(api_key=self.api_key, timeout=CLAUDE_REQUEST_TIMEOUT_SECONDS)
        try:
            response = client.messages.create(
                model=self.model,
                max_tokens=8192,
                messages=[
                    {
                        "role": "user",
                        "content": prompt,
                    }
                ],
            )
        except Exception as exc:
            elapsed_ms = int((time.perf_counter() - start) * 1000)
            print(f"[CLAUDE DEBUG] generate-commands failed after {elapsed_ms}ms", flush=True)
            logger.exception("CLAUDE generate-commands failed after %dms", elapsed_ms)
            if _is_timeout_error(exc):
                raise ClaudeTimeoutError(
                    f"Claude request timed out after {int(CLAUDE_REQUEST_TIMEOUT_SECONDS)} seconds. Please retry."
                ) from exc
            raise

        output_text = ""
        for block in (response.content or []):
            if getattr(block, "type", "") == "text":
                output_text += getattr(block, "text", "")
        output_text = output_text.strip()

        elapsed_ms = int((time.perf_counter() - start) * 1000)
        print(
            f"[CLAUDE DEBUG] generate-commands response model={self.model} elapsed_ms={elapsed_ms} output_chars={len(output_text)}",
            flush=True,
        )
        logger.debug(
            "CLAUDE generate-commands response model=%s elapsed_ms=%d output_chars=%d",
            self.model,
            elapsed_ms,
            len(output_text),
        )

        if not output_text:
            raise RuntimeError("Claude returned an empty response")

        return output_text
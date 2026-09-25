"""Fresh, tool-free GPT-5.6 Sol request boundary for one PDF."""
from dataclasses import dataclass
import base64
import json
import os
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .schemas import Identity


class CredentialUnavailable(RuntimeError):
    pass


class ModelCallError(RuntimeError):
    pass


# These are the model IDs accepted by the installed Codex catalog and the
# corresponding reasoning levels supported by the current model family.
SUPPORTED_MODELS = {
    "gpt-5.6-sol": {"none", "low", "medium", "high", "xhigh", "max"},
    "gpt-5.6-luna": {"none", "low", "medium", "high", "xhigh", "max"},
}


@dataclass(frozen=True)
class SolGradingInput:
    identity: Identity
    pdf_bytes: bytes
    pdf_sha256: str
    essay_question: str | None
    criteria: tuple[str, ...]
    ratings: tuple[str, ...]
    rubric: dict
    text_limits: dict
    response_schema: dict
    prompt: str
    prompt_version: str
    reference_example: str
    reference_version: str
    rubric_version: str
    schema_version: str


class ResponsesHttpTransport:
    """Small standard-library transport; API keys remain only in memory."""
    def __init__(self, api_key: str | None = None, base_url: str | None = None):
        self._api_key = api_key if api_key is not None else os.environ.get("OPENAI_API_KEY")
        self._base_url = (base_url or os.environ.get("OPENAI_BASE_URL") or "https://api.openai.com/v1").rstrip("/")

    def ensure_ready(self):
        if not self._api_key:
            raise CredentialUnavailable("OPENAI_API_KEY is not available to the Python process")

    def __call__(self, payload: dict, timeout_seconds: int) -> dict:
        self.ensure_ready()
        request = Request(
            self._base_url + "/responses",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Authorization": "Bearer " + self._api_key, "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            # Do not include response bodies: providers can echo request data or secrets.
            raise ModelCallError(f"Responses API HTTP {exc.code}") from None
        except (URLError, TimeoutError) as exc:
            raise ModelCallError(f"Responses API request failed: {type(exc).__name__}") from None


class SolGrader:
    """Implements the replaceable Grader method without exposing filesystem tools."""
    def __init__(self, *, model="gpt-5.6-sol", reasoning_effort="medium", timeout_seconds=180,
                 transport: Callable[[dict, int], dict] | None = None):
        if model not in SUPPORTED_MODELS:
            raise ValueError(f"Unsupported calibration model: {model}")
        if reasoning_effort not in SUPPORTED_MODELS[model]:
            raise ValueError(f"Unsupported reasoning effort {reasoning_effort!r} for {model}")
        self.model = model
        self.reasoning_effort = reasoning_effort
        self.timeout_seconds = timeout_seconds
        self.transport = transport or ResponsesHttpTransport()

    def ensure_ready(self):
        checker = getattr(self.transport, "ensure_ready", None)
        if checker:
            checker()

    def build_payload(self, request: SolGradingInput) -> dict:
        return {
            "model": self.model,
            "reasoning": {"effort": self.reasoning_effort},
            "store": False,
            "input": [{
                "role": "user",
                "content": [
                    {"type": "input_text", "text": request.prompt},
                    {"type": "input_file", "filename": "source.pdf", "file_data": "data:application/pdf;base64," + base64.b64encode(request.pdf_bytes).decode("ascii")},
                ],
            }],
            "text": {"format": {"type": "json_schema", "name": "essay_calibration", "strict": True, "schema": request.response_schema}},
            "metadata": {
                "prompt_version": request.prompt_version,
                "reference_version": request.reference_version,
                "rubric_version": request.rubric_version,
                "schema_version": request.schema_version,
                "source_sha256": request.pdf_sha256,
            },
        }

    def grade(self, request: SolGradingInput) -> dict:
        """Make exactly one transport call. Retry policy belongs nowhere here."""
        return self.transport(self.build_payload(request), self.timeout_seconds)


def extract_output_text(raw_response: Any) -> str:
    if not isinstance(raw_response, dict):
        raise ValueError("Model response must be a JSON object")
    if isinstance(raw_response.get("output_text"), str):
        return raw_response["output_text"]
    for item in raw_response.get("output", []):
        if not isinstance(item, dict):
            continue
        for content in item.get("content", []):
            if isinstance(content, dict) and content.get("type") == "output_text" and isinstance(content.get("text"), str):
                return content["text"]
    raise ValueError("Model response contains no output_text")

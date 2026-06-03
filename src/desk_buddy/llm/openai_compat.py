import requests

from .base import LLMError, LLMProvider


class OpenAICompatibleProvider(LLMProvider):
    """Talks to any OpenAI-compatible /chat/completions endpoint."""

    def __init__(self, base_url: str, model: str, api_key: str, timeout: int = 30):
        self._url = base_url.rstrip("/") + "/chat/completions"
        self._model = model
        self._api_key = api_key
        self._timeout = timeout

    def chat(self, system: str, user: str) -> str:
        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0,
        }
        headers = {"Authorization": f"Bearer {self._api_key}"}
        try:
            resp = requests.post(self._url, json=payload, headers=headers,
                                 timeout=self._timeout)
        except requests.RequestException as exc:
            raise LLMError(f"request failed: {exc}") from exc
        if resp.status_code != 200:
            raise LLMError(f"HTTP {resp.status_code}: {resp.json()}")
        try:
            return resp.json()["choices"][0]["message"]["content"]
        except (KeyError, IndexError, ValueError) as exc:
            raise LLMError(f"bad response shape: {exc}") from exc

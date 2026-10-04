"""HTTP client the Streamlit UI uses to talk to the API (D10: the UI never imports the Agent).

Every failure becomes one of two exceptions with a readable message, so the UI
can show a clear notice instead of a Python traceback:
  * ApiUnavailable — the API cannot be reached or timed out
  * ApiResponseError — the API answered with an error ({"error", "message", "trace_id"})
"""

from __future__ import annotations

from typing import Any

import httpx

from app.core.config import get_settings


class ApiUnavailable(RuntimeError):
    pass


class ApiResponseError(RuntimeError):
    def __init__(self, status_code: int, error: str, message: str, trace_id: str | None):
        super().__init__(f"{status_code} {error}: {message}")
        self.status_code, self.error, self.message, self.trace_id = status_code, error, message, trace_id


class ApiClient:
    def __init__(self, base_url: str, timeout_seconds: float = 60, transport: httpx.BaseTransport | None = None):
        self._client = httpx.Client(base_url=base_url, timeout=timeout_seconds, transport=transport)

    def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        try:
            response = self._client.request(method, path, **kwargs)
        except (httpx.ConnectError, httpx.TimeoutException, httpx.NetworkError) as error:
            raise ApiUnavailable(str(error)) from None
        if response.status_code >= 400:
            try:
                body = response.json()
            except ValueError:
                body = {}
            raise ApiResponseError(response.status_code, body.get("error", "http_error"),
                                   body.get("message", response.text[:200]), body.get("trace_id"))
        return response.json()

    def health(self) -> dict[str, Any]:
        return self._request("GET", "/health")

    def validation(self, **filters: Any) -> dict[str, Any]:
        params = {k: v for k, v in filters.items() if v is not None}
        return self._request("GET", "/validation", params=params)

    def chat(self, message: str, session_id: str | None = None) -> dict[str, Any]:
        body: dict[str, Any] = {"message": message}
        if session_id:
            body["session_id"] = session_id
        return self._request("POST", "/chat", json=body)


def make_client() -> ApiClient:
    """Client configured from settings. Tests replace this function with a fake."""
    settings = get_settings()
    return ApiClient(settings.api_base_url, settings.api_timeout_seconds)

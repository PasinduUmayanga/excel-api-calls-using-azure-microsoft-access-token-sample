"""httpx-based Sender implementation with authentication support."""

from __future__ import annotations

import base64
import time

import httpx

from apirunner.core.models import AuthConfig, AuthType, CallResult, CallStatus, PreparedRequest

AZURE_TOKEN_URL = "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"


class AzureTokenProvider:
    """Client-credentials token for Azure AD / Microsoft Entra ID, cached until shortly before expiry."""

    def __init__(self) -> None:
        self._cache: dict[tuple[str, str, str], tuple[str, float]] = {}

    async def get(self, client: httpx.AsyncClient, auth: AuthConfig) -> str:
        key = (auth.tenant_id, auth.client_id, auth.scope)
        token, expires = self._cache.get(key, ("", 0.0))
        if token and time.time() < expires - 60:
            return token
        resp = await client.post(
            AZURE_TOKEN_URL.format(tenant=auth.tenant_id),
            data={
                "grant_type": "client_credentials",
                "client_id": auth.client_id,
                "client_secret": auth.client_secret,
                "scope": auth.scope or "https://graph.microsoft.com/.default",
            },
        )
        resp.raise_for_status()
        data = resp.json()
        self._cache[key] = (data["access_token"], time.time() + float(data.get("expires_in", 3600)))
        return data["access_token"]


class HttpSender:
    """One attempt per call; used by core.executor for retries and concurrency."""

    def __init__(self, auth: AuthConfig | None = None, client: httpx.AsyncClient | None = None) -> None:
        self.auth = auth or AuthConfig()
        self._client = client
        self._azure = AzureTokenProvider()

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(follow_redirects=True)
        return self._client

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def _apply_auth(self, client: httpx.AsyncClient, headers: dict[str, str], params: dict[str, str]) -> None:
        a = self.auth
        if a.type == AuthType.BEARER and a.token:
            headers.setdefault("Authorization", f"Bearer {a.token}")
        elif a.type == AuthType.API_KEY and a.key_value:
            (headers if a.key_in == "header" else params)[a.key_name] = a.key_value
        elif a.type == AuthType.BASIC:
            raw = base64.b64encode(f"{a.username}:{a.password}".encode()).decode()
            headers.setdefault("Authorization", f"Basic {raw}")
        elif a.type == AuthType.AZURE_AD:
            headers.setdefault("Authorization", f"Bearer {await self._azure.get(client, a)}")

    async def __call__(self, request: PreparedRequest, timeout: float) -> CallResult:
        client = await self._get_client()
        headers, params = dict(request.headers), dict(request.params)
        start = time.perf_counter()
        try:
            await self._apply_auth(client, headers, params)
            resp = await client.request(
                request.method,
                request.url,
                headers=headers,
                params=params or None,
                json=request.json_body if request.json_body is not None else None,
                content=request.text_body if request.json_body is None and request.text_body else None,
                timeout=timeout,
            )
            return CallResult(
                status=CallStatus.SUCCESS if resp.is_success else CallStatus.FAILED,
                http_code=resp.status_code,
                response_text=resp.text,
                response_headers=dict(resp.headers),
                error="" if resp.is_success else f"HTTP {resp.status_code} {resp.reason_phrase}",
                elapsed_ms=(time.perf_counter() - start) * 1000,
            )
        except Exception as exc:  # network error, timeout, auth failure, invalid URL
            return CallResult(
                status=CallStatus.FAILED,
                error=f"{type(exc).__name__}: {exc}" if str(exc) else type(exc).__name__,
                elapsed_ms=(time.perf_counter() - start) * 1000,
            )

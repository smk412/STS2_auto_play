from __future__ import annotations

import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class BridgeError(RuntimeError):
    """Raised when the local STS2 bridge cannot return a usable response."""


class Sts2BridgeClient:
    """실행 중인 STS2MCP의 단일 플레이 API와 통신한다."""

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:15526",
        timeout_seconds: float = 5.0,
    ) -> None:
        """브리지 기본 주소와 HTTP 요청 제한 시간을 저장한다."""
        self._state_url = f"{base_url.rstrip('/')}/api/v1/singleplayer"
        self._timeout_seconds = timeout_seconds

    def get_state(self) -> dict[str, Any]:
        """브리지에서 현재 게임 상태를 JSON 객체로 조회한다."""
        request = Request(self._state_url, method="GET")
        try:
            with urlopen(request, timeout=self._timeout_seconds) as response:
                payload = json.load(response)
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise BridgeError(f"STS2 상태 조회 실패: {exc}") from exc

        if not isinstance(payload, dict):
            raise BridgeError("STS2 상태 응답이 JSON 객체가 아닙니다.")
        return payload

    def perform_action(self, action: dict[str, Any]) -> dict[str, Any]:
        """카드 사용이나 턴 종료 같은 행동 하나를 브리지에 전송한다."""
        body = json.dumps(action).encode("utf-8")
        request = Request(
            self._state_url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=self._timeout_seconds) as response:
                payload = json.load(response)
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise BridgeError(f"STS2 행동 실행 실패: {exc}") from exc

        if not isinstance(payload, dict) or payload.get("status") != "ok":
            raise BridgeError(f"STS2가 행동을 거부했습니다: {payload!r}")
        return payload

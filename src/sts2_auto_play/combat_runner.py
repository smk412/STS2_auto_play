from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .client import Sts2BridgeClient
from .observation import (
    COMBAT_STATE_TYPES,
    ObservationError,
    build_fair_observation,
    combat_summary,
    decision_fingerprint,
)
from .rule_agent import BasicCombatRuleAgent, action_payload


@dataclass(frozen=True)
class CombatRunResult:
    """자동 전투의 종료 상태, 행동 수와 로그 위치를 보관한다."""

    status: str
    actions: int
    final_state_type: str
    log_path: str | None

    def to_dict(self) -> dict[str, Any]:
        """CLI에서 JSON으로 출력할 수 있도록 결과를 딕셔너리로 변환한다."""
        return {
            "status": self.status,
            "actions": self.actions,
            "final_state_type": self.final_state_type,
            "log_path": self.log_path,
        }


class CombatSafetyError(RuntimeError):
    """Raised when continuing automation is not demonstrably safe."""


class JsonlCombatLogger:
    """자동 전투 이벤트를 한 줄에 JSON 하나씩 JSONL 파일에 기록한다."""

    def __init__(self, path: Path) -> None:
        """로그 파일 경로를 저장하고 필요한 부모 디렉터리를 생성한다."""
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def write(self, event: str, **fields: Any) -> None:
        """UTC 시각과 이벤트 이름, 추가 필드를 로그 파일 끝에 한 줄로 추가한다."""
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event": event,
            **fields,
        }
        with self.path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, ensure_ascii=False) + "\n")


def default_log_path() -> Path:
    """현재 시각을 포함한 기본 전투 로그 파일 경로를 만든다."""
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return Path("logs") / f"combat-{stamp}.jsonl"


class CombatRunner:
    """상태 조회, 판단, 행동 실행을 반복하여 전투 하나를 안전하게 진행한다."""

    def __init__(
        self,
        client: Sts2BridgeClient,
        agent: BasicCombatRuleAgent | None = None,
        *,
        max_actions: int = 100,
        poll_interval: float = 0.2,
        transition_timeout: float = 12.0,
        stable_samples: int = 3,
        sleeper: Callable[[float], None] = time.sleep,
        logger: JsonlCombatLogger | None = None,
    ) -> None:
        """브리지와 AI, 실행 제한, 상태 확인 및 로그 설정을 주입받는다."""
        self.client = client
        self.agent = agent or BasicCombatRuleAgent()
        self.max_actions = max_actions
        self.poll_interval = poll_interval
        self.transition_timeout = transition_timeout
        self.stable_samples = stable_samples
        self._sleep = sleeper
        self.logger = logger

    def _log(self, event: str, **fields: Any) -> None:
        """로거가 설정된 경우에만 전투 이벤트를 기록한다."""
        if self.logger:
            self.logger.write(event, **fields)

    def _stable_observation(
        self,
        *,
        previous: tuple[Any, ...] | None = None,
        after_end_turn: bool = False,
    ) -> tuple[dict[str, Any] | None, dict[str, Any]]:
        """연속으로 동일한 플레이어 상태가 관측될 때까지 기다린다."""
        deadline = time.monotonic() + self.transition_timeout
        last_fingerprint: tuple[Any, ...] | None = None
        consecutive = 0
        last_raw: dict[str, Any] = {}

        while time.monotonic() < deadline:
            last_raw = self.client.get_state()
            state_type = last_raw.get("state_type")
            if state_type not in COMBAT_STATE_TYPES:
                # A non-combat state is only accepted after two matching reads;
                # this avoids treating a transient blank screen as completion.
                marker = ("non_combat", state_type)
                consecutive = consecutive + 1 if marker == last_fingerprint else 1
                last_fingerprint = marker
                if consecutive >= 2:
                    return None, last_raw
                self._sleep(self.poll_interval)
                continue

            try:
                observation = build_fair_observation(last_raw)
            except ObservationError:
                self._sleep(self.poll_interval)
                continue

            fingerprint = decision_fingerprint(observation)
            battle = observation["battle"]
            player = observation["player"]
            ready = battle.get("turn") == "player" and battle.get("is_play_phase")
            if after_end_turn:
                ready = ready and bool(player.get("hand"))
            changed = previous is None or fingerprint != previous

            if ready and changed:
                consecutive = consecutive + 1 if fingerprint == last_fingerprint else 1
                last_fingerprint = fingerprint
                if consecutive >= self.stable_samples:
                    return observation, last_raw
            else:
                consecutive = 0
                last_fingerprint = fingerprint
            self._sleep(self.poll_interval)

        raise CombatSafetyError(
            f"{self.transition_timeout:g}초 안에 안정된 다음 상태를 확인하지 못했습니다."
        )

    def run(self) -> CombatRunResult:
        """안전 조건을 검사하며 전투 종료 또는 중단 조건까지 행동을 반복한다."""
        observation, raw = self._stable_observation()
        if observation is None:
            raise CombatSafetyError(f"전투 상태에서 시작해야 합니다: {raw.get('state_type')!r}")

        repeated: dict[tuple[Any, ...], int] = {}
        self._log("combat_started", state=combat_summary(observation))

        for action_number in range(1, self.max_actions + 1):
            fingerprint = decision_fingerprint(observation)
            repeated[fingerprint] = repeated.get(fingerprint, 0) + 1
            if repeated[fingerprint] > 2:
                raise CombatSafetyError("동일한 의사결정 상태가 반복되어 자동 실행을 중단했습니다.")

            recommendation = self.agent.recommend(observation)
            payload = action_payload(recommendation)

            # Final stale-state guard immediately before each mutation.
            latest = build_fair_observation(self.client.get_state())
            if decision_fingerprint(latest) != fingerprint:
                raise CombatSafetyError("행동 직전 상태가 변경되어 자동 실행을 중단했습니다.")

            response = self.client.perform_action(payload)
            self._log(
                "action",
                number=action_number,
                before=combat_summary(observation),
                recommendation=recommendation.to_dict(),
                response=response,
            )

            observation, raw = self._stable_observation(
                previous=fingerprint,
                after_end_turn=recommendation.action == "end_turn",
            )
            if observation is None:
                final_type = str(raw.get("state_type") or "unknown")
                self._log("combat_finished", actions=action_number, final_state_type=final_type)
                return CombatRunResult(
                    status="completed",
                    actions=action_number,
                    final_state_type=final_type,
                    log_path=str(self.logger.path) if self.logger else None,
                )

        raise CombatSafetyError(f"최대 행동 횟수 {self.max_actions}에 도달해 중단했습니다.")

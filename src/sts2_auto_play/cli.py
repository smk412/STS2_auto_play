from __future__ import annotations

import argparse
import json
import sys
import time

from .client import BridgeError, Sts2BridgeClient
from .combat_runner import CombatRunner, CombatSafetyError, JsonlCombatLogger, default_log_path
from .observation import (
    ObservationError,
    build_fair_observation,
    combat_summary,
    decision_fingerprint,
)
from .rule_agent import BasicCombatRuleAgent, action_payload


def _parse_args() -> argparse.Namespace:
    """추천, 단일 실행, 자동 전투에 필요한 명령행 옵션을 해석한다."""
    parser = argparse.ArgumentParser(description="STS2 Rule AI recommendation-only CLI")
    parser.add_argument("--base-url", default="http://127.0.0.1:15526")
    parser.add_argument("--stability-delay", type=float, default=0.25)
    parser.add_argument("--show-observation", action="store_true")
    parser.add_argument(
        "--execute",
        action="store_true",
        help="추천한 행동 하나를 실제 게임에 전송합니다.",
    )
    parser.add_argument(
        "--auto-combat",
        action="store_true",
        help="현재 전투가 끝날 때까지 Rule AI를 반복 실행합니다.",
    )
    parser.add_argument("--max-actions", type=int, default=100)
    return parser.parse_args()


def main() -> int:
    """CLI 모드에 따라 추천, 단일 행동 또는 자동 전투를 실행한다."""
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = _parse_args()
    client = Sts2BridgeClient(args.base_url)
    if args.execute and args.auto_combat:
        print(json.dumps({"status": "error", "error": "--execute와 --auto-combat은 함께 사용할 수 없습니다."}, ensure_ascii=False, indent=2))
        return 2

    if args.auto_combat:
        log_path = default_log_path()
        try:
            result = CombatRunner(
                client,
                max_actions=args.max_actions,
                logger=JsonlCombatLogger(log_path),
            ).run()
        except (BridgeError, ObservationError, ValueError, CombatSafetyError) as exc:
            print(json.dumps({"status": "stopped", "error": str(exc), "log_path": str(log_path)}, ensure_ascii=False, indent=2))
            return 2
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
        return 0

    try:
        first = build_fair_observation(client.get_state())
        time.sleep(max(0.0, args.stability_delay))
        second = build_fair_observation(client.get_state())
        if decision_fingerprint(first) != decision_fingerprint(second):
            raise ObservationError("두 번의 상태 조회가 일치하지 않습니다. 잠시 후 다시 실행하세요.")
        recommendation = BasicCombatRuleAgent().recommend(second)

        execution = None
        after = None
        if args.execute:
            # Re-read immediately before POST so a hand index from an older
            # snapshot is never sent after the game state changes.
            latest = build_fair_observation(client.get_state())
            if decision_fingerprint(second) != decision_fingerprint(latest):
                raise ObservationError("행동 전 상태가 변경되어 실행을 취소했습니다.")
            execution = client.perform_action(action_payload(recommendation))

            before_fingerprint = decision_fingerprint(latest)
            deadline = time.monotonic() + 5.0
            while time.monotonic() < deadline:
                time.sleep(0.2)
                candidate = build_fair_observation(client.get_state())
                if decision_fingerprint(candidate) != before_fingerprint:
                    after = candidate
                    break
            if after is None:
                raise ObservationError("행동 후 5초 동안 상태 변화를 확인하지 못했습니다.")
    except (BridgeError, ObservationError, ValueError) as exc:
        print(json.dumps({"status": "not_ready", "error": str(exc)}, ensure_ascii=False, indent=2))
        return 2

    result = {
        "status": "ok",
        "mode": "execute_one" if args.execute else "recommendation_only",
        "recommendation": recommendation.to_dict(),
    }
    if args.execute:
        result["execution"] = execution
        result["before"] = combat_summary(second)
        result["after"] = combat_summary(after)
    if args.show_observation:
        result["fair_observation"] = second
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class Recommendation:
    """Rule AI가 선택한 행동과 선택 이유를 표현한다."""

    action: str
    card_index: int | None = None
    target: str | None = None
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        """값이 없는 선택 필드를 제외하고 일반 딕셔너리로 변환한다."""
        return {key: value for key, value in asdict(self).items() if value is not None}


def _number(value: Any) -> int:
    """문자열 또는 숫자 값을 안전하게 정수로 변환하며 실패하면 0을 반환한다."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _incoming_attack(enemies: list[dict[str, Any]]) -> int:
    """모든 적이 공개한 공격 의도를 합산해 이번 턴 예상 피해를 계산한다."""
    total = 0
    for enemy in enemies:
        for intent in enemy.get("intents") or []:
            if intent.get("type") != "Attack":
                continue
            label = str(intent.get("label") or "0").lower().replace("×", "x")
            if "x" in label:
                parts = label.split("x", 1)
                total += _number(parts[0]) * _number(parts[1])
            else:
                total += _number(label)
    return total


def _energy_cost(card: dict[str, Any]) -> int:
    """카드의 현재 에너지 비용을 정수로 반환한다."""
    return _number(card.get("cost"))


def _weakest_enemy(enemies: list[dict[str, Any]]) -> dict[str, Any] | None:
    """살아 있는 적 중 현재 HP가 가장 낮은 적을 선택한다."""
    living = [enemy for enemy in enemies if _number(enemy.get("hp")) > 0]
    return min(living, key=lambda enemy: _number(enemy.get("hp")), default=None)


class BasicCombatRuleAgent:
    """아이언클래드 초기 전투를 위한 작고 설명 가능한 기준선 Rule AI다."""

    def recommend(self, observation: dict[str, Any]) -> Recommendation:
        """공개된 전투 상태를 평가해 다음 행동 하나를 추천한다."""
        battle = observation["battle"]
        player = observation["player"]
        hand = player["hand"]

        if battle.get("turn") != "player" or not battle.get("is_play_phase"):
            raise ValueError("아직 플레이어가 행동할 수 있는 안정된 상태가 아닙니다.")
        if not hand or _number(player.get("energy")) <= 0:
            return Recommendation("end_turn", reason="사용할 수 있는 카드 또는 에너지가 없습니다.")

        playable = [card for card in hand if card.get("can_play")]
        incoming = _incoming_attack(battle["enemies"])
        block_gap = max(0, incoming - _number(player.get("block")))

        defends = [card for card in playable if str(card.get("id", "")).startswith("DEFEND")]
        if block_gap > 0 and defends:
            card = min(defends, key=_energy_cost)
            return Recommendation(
                "play_card",
                card_index=int(card["index"]),
                reason=f"공개된 예상 피해 {incoming}에 비해 방어도가 {player.get('block')}이므로 방어를 우선합니다.",
            )

        enemy = _weakest_enemy(battle["enemies"])
        attacks = [card for card in playable if card.get("type") == "Attack"]
        if attacks and enemy:
            bash = next((card for card in attacks if card.get("id") == "BASH"), None)
            card = bash or min(attacks, key=_energy_cost)
            return Recommendation(
                "play_card",
                card_index=int(card["index"]),
                target=str(enemy["entity_id"]),
                reason=f"현재 방어 우선 조건을 충족했으므로 {enemy.get('name')}에게 공격합니다.",
            )

        return Recommendation("end_turn", reason="현재 규칙으로 안전하게 사용할 카드를 찾지 못했습니다.")


def action_payload(recommendation: Recommendation) -> dict[str, Any]:
    """내부 Recommendation을 STS2MCP가 받는 행동 JSON 형태로 변환한다."""
    allowed_actions = {"play_card", "end_turn"}
    if recommendation.action not in allowed_actions:
        raise ValueError(f"허용되지 않은 행동입니다: {recommendation.action}")

    payload: dict[str, Any] = {"action": recommendation.action}
    if recommendation.action == "play_card":
        if recommendation.card_index is None:
            raise ValueError("카드 실행에는 card_index가 필요합니다.")
        payload["card_index"] = recommendation.card_index
        if recommendation.target is not None:
            payload["target"] = recommendation.target
    return payload

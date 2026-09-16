from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from .card_effects import effect_for


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


def _enemy_attack(enemy: dict[str, Any]) -> int:
    """적 하나가 공개한 이번 턴 공격 피해를 계산한다."""
    return _incoming_attack([enemy])


def _energy_cost(card: dict[str, Any]) -> int:
    """카드의 현재 에너지 비용을 정수로 반환한다."""
    return _number(card.get("cost"))


def _has_vulnerable(enemy: dict[str, Any]) -> bool:
    """공개된 상태 목록에서 적에게 취약이 적용됐는지 확인한다."""
    for status in enemy.get("status") or []:
        identity = " ".join(
            str(status.get(key) or "") for key in ("id", "name", "title")
        ).upper()
        if "VULNERABLE" in identity or "취약" in identity:
            amount = status.get("amount", status.get("count", status.get("stacks", 1)))
            return _number(amount) > 0
    return False


def _card_values(card: dict[str, Any]) -> tuple[int, int, int]:
    """지원 카드의 현재 피해, 방어도, 취약 수치를 반환한다."""
    effect = effect_for(card)
    if effect is None:
        return 0, 0, 0
    return effect.values(bool(card.get("is_upgraded")))


def _apply_damage(hp: int, block: int, damage: int) -> tuple[int, int]:
    """피해를 방어도에 먼저 적용한 뒤 남은 HP와 방어도를 반환한다."""
    absorbed = min(block, damage)
    return hp - (damage - absorbed), block - absorbed


def _lethal_sequence(
    cards: list[dict[str, Any]],
    enemy: dict[str, Any],
    energy: int,
) -> list[dict[str, Any]] | None:
    """현재 에너지로 적을 처치할 수 있는 가장 저렴한 공격 순서를 찾는다."""
    attacks = [card for card in cards if _card_values(card)[0] > 0]
    best: tuple[tuple[int, int], list[dict[str, Any]]] | None = None

    def search(
        remaining: list[dict[str, Any]],
        energy_left: int,
        hp: int,
        block: int,
        vulnerable: bool,
        sequence: list[dict[str, Any]],
        spent: int,
    ) -> None:
        """남은 공격 카드 순서를 재귀적으로 순회하며 처치 가능한 계획을 갱신한다."""
        nonlocal best
        if hp <= 0:
            score = (spent, len(sequence))
            if best is None or score < best[0]:
                best = (score, list(sequence))
            return

        for position, card in enumerate(remaining):
            cost = _energy_cost(card)
            if cost > energy_left:
                continue
            damage, _, vulnerable_turns = _card_values(card)
            actual_damage = int(damage * 1.5) if vulnerable else damage
            next_hp, next_block = _apply_damage(hp, block, actual_damage)
            search(
                remaining[:position] + remaining[position + 1 :],
                energy_left - cost,
                next_hp,
                next_block,
                vulnerable or vulnerable_turns > 0,
                sequence + [card],
                spent + cost,
            )

    search(
        attacks,
        energy,
        _number(enemy.get("hp")),
        _number(enemy.get("block")),
        _has_vulnerable(enemy),
        [],
        0,
    )
    return best[1] if best else None


def _lethal_plan(
    cards: list[dict[str, Any]],
    enemies: list[dict[str, Any]],
    energy: int,
) -> tuple[dict[str, Any], list[dict[str, Any]]] | None:
    """여러 적 중 처치 가능한 대상을 골라 공격 순서와 함께 반환한다."""
    candidates: list[tuple[tuple[int, int, int, int], dict[str, Any], list[dict[str, Any]]]] = []
    for enemy in enemies:
        if _number(enemy.get("hp")) <= 0:
            continue
        sequence = _lethal_sequence(cards, enemy, energy)
        if sequence:
            energy_cost = sum(_energy_cost(card) for card in sequence)
            score = (
                energy_cost,
                len(sequence),
                -_enemy_attack(enemy),
                _number(enemy.get("hp")),
            )
            candidates.append((score, enemy, sequence))
    if not candidates:
        return None
    _, enemy, sequence = min(candidates, key=lambda item: item[0])
    return enemy, sequence


def _priority_enemy(enemies: list[dict[str, Any]]) -> dict[str, Any] | None:
    """공격 의도가 큰 적을 우선하고 동률이면 HP가 낮은 적을 선택한다."""
    living = [enemy for enemy in enemies if _number(enemy.get("hp")) > 0]
    return min(
        living,
        key=lambda enemy: (-_enemy_attack(enemy), _number(enemy.get("hp"))),
        default=None,
    )


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
        energy = _number(player.get("energy"))
        lethal = _lethal_plan(playable, battle["enemies"], energy)
        if lethal:
            enemy, sequence = lethal
            card = sequence[0]
            return Recommendation(
                "play_card",
                card_index=int(card["index"]),
                target=str(enemy["entity_id"]),
                reason=f"현재 손패와 에너지로 {enemy.get('name')}을 처치할 수 있어 공격을 우선합니다.",
            )

        incoming = _incoming_attack(battle["enemies"])
        block_gap = max(0, incoming - _number(player.get("block")))

        defends = [card for card in playable if _card_values(card)[1] > 0]
        if block_gap > 0 and defends:
            def defense_priority(candidate: dict[str, Any]) -> tuple[int, int, int]:
                """필요 방어량 충족 여부, 낭비 또는 부족량, 비용 순으로 정렬한다."""
                block_value = _card_values(candidate)[1]
                if block_value >= block_gap:
                    return 0, block_value - block_gap, _energy_cost(candidate)
                return 1, -block_value, _energy_cost(candidate)

            card = min(
                defends,
                key=defense_priority,
            )
            return Recommendation(
                "play_card",
                card_index=int(card["index"]),
                reason=f"공개된 예상 피해 {incoming}에 비해 방어도가 {player.get('block')}이므로 방어를 우선합니다.",
            )

        enemy = _priority_enemy(battle["enemies"])
        attacks = [card for card in playable if _card_values(card)[0] > 0]
        if attacks and enemy:
            bash = next(
                (
                    card
                    for card in attacks
                    if card.get("id") == "BASH" and not _has_vulnerable(enemy)
                ),
                None,
            )
            card = bash or max(
                attacks,
                key=lambda candidate: (
                    _card_values(candidate)[0] / max(1, _energy_cost(candidate)),
                    _card_values(candidate)[0],
                ),
            )
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

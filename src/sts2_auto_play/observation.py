from __future__ import annotations

from collections import Counter
from typing import Any


COMBAT_STATE_TYPES = {"monster", "elite", "boss"}


class ObservationError(ValueError):
    """Raised when raw bridge state cannot form a fair combat observation."""


def _public_card(card: dict[str, Any]) -> dict[str, Any]:
    """원본 카드 데이터에서 AI가 사용해도 되는 공개 필드만 복사한다."""
    allowed = (
        "id",
        "name",
        "type",
        "cost",
        "star_cost",
        "description",
        "rarity",
        "is_upgraded",
        "keywords",
        "index",
        "target_type",
        "can_play",
        "unplayable_reason",
    )
    return {key: card.get(key) for key in allowed if key in card}


def _unordered_card_counts(cards: list[dict[str, Any]]) -> dict[str, int]:
    """카드 배열의 순서를 제거하고 카드 이름별 장수로 집계한다."""
    names = (str(card.get("name") or card.get("id") or "UNKNOWN") for card in cards)
    return dict(sorted(Counter(names).items()))


def build_fair_observation(raw: dict[str, Any]) -> dict[str, Any]:
    """브리지 원본 상태를 공개 정보만 포함한 전투 Observation으로 변환한다."""
    state_type = raw.get("state_type")
    if state_type not in COMBAT_STATE_TYPES:
        raise ObservationError(f"전투 상태가 아닙니다: {state_type!r}")

    battle = raw.get("battle") or {}
    player = raw.get("player") or {}
    enemies = battle.get("enemies") or []
    hand = player.get("hand") or []

    if not isinstance(enemies, list) or not isinstance(hand, list):
        raise ObservationError("적 또는 손패 데이터 형식이 올바르지 않습니다.")

    piles: dict[str, Any] = {}
    for pile_name in ("draw_pile", "discard_pile", "exhaust_pile"):
        cards = player.get(pile_name) or []
        # The bridge array may preserve a hidden engine order. Keep only an
        # order-free multiset plus the visible count.
        piles[pile_name] = {
            "count": int(player.get(f"{pile_name}_count", len(cards))),
            "known_composition": _unordered_card_counts(cards),
        }

    return {
        "state_type": state_type,
        "run": {
            key: raw.get("run", {}).get(key)
            for key in ("act", "floor", "ascension")
        },
        "battle": {
            "round": battle.get("round"),
            "turn": battle.get("turn"),
            "is_play_phase": bool(battle.get("is_play_phase")),
            "enemies": [
                {
                    key: enemy.get(key)
                    for key in (
                        "entity_id",
                        "name",
                        "hp",
                        "max_hp",
                        "block",
                        "status",
                        "intents",
                    )
                }
                for enemy in enemies
            ],
        },
        "player": {
            key: player.get(key)
            for key in (
                "character",
                "hp",
                "max_hp",
                "block",
                "energy",
                "max_energy",
                "status",
                "relics",
                "potions",
                "max_potion_slots",
            )
        }
        | {
            "hand": [_public_card(card) for card in hand],
            "piles": piles,
        },
    }


def decision_fingerprint(observation: dict[str, Any]) -> tuple[Any, ...]:
    """행동 결정에 중요한 값들을 비교 가능한 불변 튜플로 만든다."""
    battle = observation["battle"]
    player = observation["player"]
    enemy_state = tuple(
        (enemy.get("entity_id"), enemy.get("hp"), enemy.get("block"), repr(enemy.get("intents")))
        for enemy in battle["enemies"]
    )
    hand_state = tuple(
        (card.get("id"), card.get("index"), card.get("cost"), card.get("can_play"))
        for card in player["hand"]
    )
    return (
        battle.get("round"),
        battle.get("turn"),
        battle.get("is_play_phase"),
        player.get("hp"),
        player.get("block"),
        player.get("energy"),
        hand_state,
        enemy_state,
    )


def combat_summary(observation: dict[str, Any]) -> dict[str, Any]:
    """로그와 실행 결과에 사용할 작은 전투 상태 요약을 만든다."""
    battle = observation["battle"]
    player = observation["player"]
    return {
        "round": battle.get("round"),
        "turn": battle.get("turn"),
        "is_play_phase": battle.get("is_play_phase"),
        "player_hp": player.get("hp"),
        "player_block": player.get("block"),
        "energy": player.get("energy"),
        "hand_count": len(player.get("hand") or []),
        "enemies": [
            {
                "entity_id": enemy.get("entity_id"),
                "hp": enemy.get("hp"),
                "block": enemy.get("block"),
            }
            for enemy in battle.get("enemies") or []
        ],
    }

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class CardEffect:
    """Rule AI 계산에 필요한 카드의 공개된 수치 효과를 표현한다."""

    damage: int = 0
    block: int = 0
    vulnerable: int = 0
    upgraded_damage: int | None = None
    upgraded_block: int | None = None
    upgraded_vulnerable: int | None = None

    def values(self, upgraded: bool) -> tuple[int, int, int]:
        """강화 여부를 반영한 피해, 방어도, 취약 수치를 반환한다."""
        if not upgraded:
            return self.damage, self.block, self.vulnerable
        return (
            self.upgraded_damage if self.upgraded_damage is not None else self.damage,
            self.upgraded_block if self.upgraded_block is not None else self.block,
            self.upgraded_vulnerable
            if self.upgraded_vulnerable is not None
            else self.vulnerable,
        )


CARD_EFFECTS: dict[str, CardEffect] = {
    "STRIKE_IRONCLAD": CardEffect(damage=6, upgraded_damage=9),
    "DEFEND_IRONCLAD": CardEffect(block=5, upgraded_block=8),
    "BASH": CardEffect(
        damage=8,
        vulnerable=2,
        upgraded_damage=10,
        upgraded_vulnerable=3,
    ),
}


def effect_for(card: dict[str, Any]) -> CardEffect | None:
    """카드 ID로 현재 Rule AI가 지원하는 구조화된 효과를 찾는다."""
    return CARD_EFFECTS.get(str(card.get("id") or ""))


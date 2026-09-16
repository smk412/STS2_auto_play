import unittest

from sts2_auto_play.rule_agent import BasicCombatRuleAgent, Recommendation, _incoming_attack, action_payload


def observation(block: int, incoming: str, energy: int = 3):
    """Rule AI 테스트에 사용할 최소 전투 Observation을 만든다."""
    return {
        "battle": {
            "turn": "player",
            "is_play_phase": True,
            "enemies": [
                {
                    "entity_id": "NIBBIT_0",
                    "name": "깨작이",
                    "hp": 44,
                    "intents": [{"type": "Attack", "label": incoming}],
                }
            ],
        },
        "player": {
            "block": block,
            "energy": energy,
            "hand": [
                {"id": "BASH", "index": 0, "type": "Attack", "cost": "2", "can_play": True},
                {"id": "DEFEND_IRONCLAD", "index": 1, "type": "Skill", "cost": "1", "can_play": True},
            ],
        },
    }


class BasicCombatRuleAgentTest(unittest.TestCase):
    """기본 전투 규칙의 주요 판단 분기를 검증한다."""

    def test_defends_against_unblocked_incoming_damage(self) -> None:
        """방어되지 않은 예상 피해가 있으면 수비를 선택하는지 확인한다."""
        result = BasicCombatRuleAgent().recommend(observation(block=0, incoming="12"))
        self.assertEqual(result.action, "play_card")
        self.assertEqual(result.card_index, 1)
        self.assertIsNone(result.target)

    def test_attacks_when_incoming_damage_is_blocked(self) -> None:
        """예상 피해를 이미 막았으면 공격을 선택하는지 확인한다."""
        result = BasicCombatRuleAgent().recommend(observation(block=12, incoming="12"))
        self.assertEqual(result.card_index, 0)
        self.assertEqual(result.target, "NIBBIT_0")

    def test_ends_turn_when_hand_is_empty(self) -> None:
        """손패와 에너지가 없으면 턴 종료를 선택하는지 확인한다."""
        state = observation(block=0, incoming="12", energy=0)
        state["player"]["hand"] = []
        self.assertEqual(BasicCombatRuleAgent().recommend(state).action, "end_turn")

    def test_multihit_intent_uses_multiplication_sign(self) -> None:
        """곱셈 기호가 포함된 다단 공격 피해를 합산하는지 확인한다."""
        enemies = [{"intents": [{"type": "Attack", "label": "6×2"}]}]
        self.assertEqual(_incoming_attack(enemies), 12)

    def test_action_payload_omits_null_target(self) -> None:
        """대상이 없는 카드 행동에서 target 필드를 제외하는지 확인한다."""
        recommendation = Recommendation("play_card", card_index=2)
        self.assertEqual(action_payload(recommendation), {"action": "play_card", "card_index": 2})


if __name__ == "__main__":
    unittest.main()

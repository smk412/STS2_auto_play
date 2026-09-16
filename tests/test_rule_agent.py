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


def card(card_id: str, index: int, cost: int = 1) -> dict:
    """카드 ID에 맞는 최소 테스트용 카드 데이터를 만든다."""
    return {
        "id": card_id,
        "index": index,
        "type": "Attack" if card_id in {"STRIKE_IRONCLAD", "BASH"} else "Skill",
        "cost": str(cost),
        "can_play": True,
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

    def test_lethal_two_strikes_are_preferred_over_defending(self) -> None:
        """공격 두 장으로 처치할 수 있으면 높은 피해 의도보다 처치를 우선한다."""
        state = observation(block=0, incoming="20", energy=2)
        state["battle"]["enemies"][0]["hp"] = 12
        state["player"]["hand"] = [
            card("DEFEND_IRONCLAD", 0),
            card("STRIKE_IRONCLAD", 1),
            card("STRIKE_IRONCLAD", 2),
        ]

        result = BasicCombatRuleAgent().recommend(state)

        self.assertIn(result.card_index, {1, 2})
        self.assertEqual(result.target, "NIBBIT_0")
        self.assertIn("처치", result.reason)

    def test_bash_is_first_when_vulnerable_combo_is_lethal(self) -> None:
        """강타 후 타격으로만 처치 가능한 경우 강타를 먼저 선택한다."""
        state = observation(block=0, incoming="20", energy=3)
        state["battle"]["enemies"][0]["hp"] = 17
        state["player"]["hand"] = [
            card("STRIKE_IRONCLAD", 0),
            card("BASH", 1, cost=2),
            card("DEFEND_IRONCLAD", 2),
        ]

        result = BasicCombatRuleAgent().recommend(state)

        self.assertEqual(result.card_index, 1)
        self.assertEqual(result.target, "NIBBIT_0")

    def test_defends_when_no_lethal_sequence_exists(self) -> None:
        """즉시 처치가 불가능하고 피해가 예상되면 필요한 방어를 우선한다."""
        state = observation(block=0, incoming="12", energy=2)
        state["battle"]["enemies"][0]["hp"] = 40
        state["player"]["hand"] = [
            card("DEFEND_IRONCLAD", 0),
            card("STRIKE_IRONCLAD", 1),
        ]

        result = BasicCombatRuleAgent().recommend(state)

        self.assertEqual(result.card_index, 0)
        self.assertIsNone(result.target)

    def test_defense_card_that_covers_gap_is_preferred(self) -> None:
        """한 장으로 필요한 방어량을 충족하는 강화 수비를 우선한다."""
        state = observation(block=0, incoming="7", energy=2)
        normal = card("DEFEND_IRONCLAD", 0)
        upgraded = card("DEFEND_IRONCLAD", 1)
        upgraded["is_upgraded"] = True
        state["player"]["hand"] = [normal, upgraded]

        result = BasicCombatRuleAgent().recommend(state)

        self.assertEqual(result.card_index, 1)

    def test_existing_vulnerable_makes_strike_lethal(self) -> None:
        """이미 적용된 취약을 공개 상태에서 읽어 공격 피해에 반영한다."""
        state = observation(block=0, incoming="20", energy=1)
        enemy = state["battle"]["enemies"][0]
        enemy["hp"] = 9
        enemy["status"] = [{"id": "VULNERABLE", "amount": 1}]
        state["player"]["hand"] = [
            card("DEFEND_IRONCLAD", 0),
            card("STRIKE_IRONCLAD", 1),
        ]

        result = BasicCombatRuleAgent().recommend(state)

        self.assertEqual(result.card_index, 1)
        self.assertIn("처치", result.reason)

    def test_killable_enemy_is_targeted_in_multi_enemy_combat(self) -> None:
        """여러 적 중 현재 에너지로 처치할 수 있는 적을 공격 대상으로 고른다."""
        state = observation(block=0, incoming="0", energy=1)
        state["battle"]["enemies"] = [
            {
                "entity_id": "SMALL_0",
                "name": "약한 적",
                "hp": 6,
                "block": 0,
                "status": [],
                "intents": [],
            },
            {
                "entity_id": "LARGE_0",
                "name": "강한 적",
                "hp": 40,
                "block": 0,
                "status": [],
                "intents": [{"type": "Attack", "label": "10"}],
            },
        ]
        state["player"]["hand"] = [card("STRIKE_IRONCLAD", 0)]

        result = BasicCombatRuleAgent().recommend(state)

        self.assertEqual(result.target, "SMALL_0")
        self.assertIn("처치", result.reason)


if __name__ == "__main__":
    unittest.main()

import unittest

from sts2_auto_play.combat_runner import CombatRunner


def raw_state(*, hp=80, enemy_hp=6, energy=1, hand=None, state_type="monster"):
    """CombatRunner 테스트에 사용할 브리지 원본 상태를 만든다."""
    if state_type != "monster":
        return {"state_type": state_type}
    return {
        "state_type": "monster",
        "run": {"act": 1, "floor": 1, "ascension": 0},
        "battle": {
            "round": 1,
            "turn": "player",
            "is_play_phase": True,
            "enemies": [
                {
                    "entity_id": "NIBBIT_0",
                    "name": "깨작이",
                    "hp": enemy_hp,
                    "max_hp": 44,
                    "block": 0,
                    "status": [],
                    "intents": [],
                }
            ],
        },
        "player": {
            "character": "아이언클래드",
            "hp": hp,
            "max_hp": 80,
            "block": 0,
            "energy": energy,
            "max_energy": 3,
            "hand": hand
            if hand is not None
            else [
                {
                    "id": "STRIKE_IRONCLAD",
                    "name": "타격",
                    "type": "Attack",
                    "cost": "1",
                    "index": 0,
                    "target_type": "AnyEnemy",
                    "can_play": True,
                }
            ],
            "draw_pile": [],
            "discard_pile": [],
            "exhaust_pile": [],
            "status": [],
            "relics": [],
            "potions": [],
        },
    }


class FakeClient:
    """실제 게임 대신 미리 준비한 상태와 행동 응답을 제공한다."""

    def __init__(self):
        """안정된 전투 상태와 전투 종료 상태의 조회 순서를 준비한다."""
        # 3 stable start reads, stale guard, then 2 stable terminal reads.
        self.states = [raw_state()] * 4 + [raw_state(state_type="rewards")] * 2
        self.actions = []

    def get_state(self):
        """준비된 상태를 호출 순서대로 하나씩 반환한다."""
        return self.states.pop(0)

    def perform_action(self, action):
        """전송된 행동을 저장하고 성공 응답을 반환한다."""
        self.actions.append(action)
        return {"status": "ok"}


class CombatRunnerTest(unittest.TestCase):
    """CombatRunner의 반복 실행 및 종료 판정을 검증한다."""

    def test_completes_when_action_reaches_rewards(self):
        """공격 후 보상 화면에 도달하면 완료 결과를 반환하는지 확인한다."""
        client = FakeClient()
        result = CombatRunner(
            client,
            stable_samples=3,
            poll_interval=0,
            sleeper=lambda _: None,
        ).run()

        self.assertEqual(result.status, "completed")
        self.assertEqual(result.actions, 1)
        self.assertEqual(result.final_state_type, "rewards")
        self.assertEqual(
            client.actions,
            [{"action": "play_card", "card_index": 0, "target": "NIBBIT_0"}],
        )


if __name__ == "__main__":
    unittest.main()

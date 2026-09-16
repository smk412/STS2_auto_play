import unittest

from sts2_auto_play.observation import build_fair_observation


class FairObservationTest(unittest.TestCase):
    """공정 Observation 변환 규칙을 검증한다."""

    def test_draw_order_is_replaced_with_counts(self) -> None:
        """뽑기 더미 순서가 제거되고 카드별 장수만 남는지 확인한다."""
        raw = {
            "state_type": "monster",
            "run": {"act": 1, "floor": 1, "ascension": 0},
            "battle": {"round": 1, "turn": "player", "is_play_phase": True, "enemies": []},
            "player": {
                "hand": [],
                "draw_pile_count": 3,
                "draw_pile": [{"name": "타격"}, {"name": "수비"}, {"name": "타격"}],
                "discard_pile": [],
                "exhaust_pile": [],
            },
        }

        observation = build_fair_observation(raw)

        draw = observation["player"]["piles"]["draw_pile"]
        self.assertEqual(draw["count"], 3)
        self.assertEqual(draw["known_composition"], {"수비": 1, "타격": 2})
        self.assertNotIn("draw_pile", observation["player"])


if __name__ == "__main__":
    unittest.main()

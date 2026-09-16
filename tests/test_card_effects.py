import unittest

from sts2_auto_play.card_effects import effect_for


class CardEffectTest(unittest.TestCase):
    """카드 ID 기반 효과 조회와 강화 수치를 검증한다."""

    def test_upgraded_bash_values(self) -> None:
        """강화된 강타의 피해와 취약 수치를 반환하는지 확인한다."""
        effect = effect_for({"id": "BASH"})

        self.assertIsNotNone(effect)
        self.assertEqual(effect.values(upgraded=True), (10, 0, 3))

    def test_unknown_card_has_no_assumed_effect(self) -> None:
        """지원하지 않는 카드는 설명을 추측하지 않고 None을 반환하는지 확인한다."""
        self.assertIsNone(effect_for({"id": "UNKNOWN_CARD"}))


if __name__ == "__main__":
    unittest.main()

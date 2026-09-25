import unittest
from workflow.state import State, STATES, transition


class StateTests(unittest.TestCase):
    def test_all_allowed_and_disallowed_transitions(self):
        for i, current in enumerate(STATES):
            for j, target in enumerate(STATES):
                with self.subTest(current=current, target=target):
                    if j == i + 1:
                        self.assertEqual(transition(current, target), target)
                    else:
                        with self.assertRaises(ValueError):
                            transition(current, target)

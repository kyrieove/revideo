import unittest

try:
    from scripts.smart_match import (
        enumerate_windows,
        score_candidate,
        score_transition,
        beam_search,
        propose
    )
    from scripts.smart_reference import derive_targets
except ImportError:
    propose = None


class TestSmartMatchRed(unittest.TestCase):
    def test_imports_exist(self):
        self.assertIsNotNone(propose, "smart_match and propose must exist")


if __name__ == "__main__":
    unittest.main()

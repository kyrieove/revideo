import unittest

try:
    from scripts.smart_workflow import approve, build_proposed_plan
    from scripts.smart_preview import generate_preview
except ImportError:
    approve = None


class TestSmartApprovalRed(unittest.TestCase):
    def test_imports_exist(self):
        self.assertIsNotNone(approve, "smart_workflow approve function must exist")


if __name__ == "__main__":
    unittest.main()

import json
import unittest
from pathlib import Path

try:
    from scripts.material_index import (
        discover_assets,
        probe_asset,
        sample_asset,
        extract_features,
        build_index,
        load_index
    )
except ImportError:
    discover_assets = None


class TestSmartIndexRed(unittest.TestCase):
    def test_imports_exist(self):
        self.assertIsNotNone(discover_assets, "material_index module and functions must exist")


if __name__ == "__main__":
    unittest.main()

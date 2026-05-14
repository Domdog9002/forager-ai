from __future__ import annotations

import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from forager_ai.catalog.indexer import build_pack_content_index


class ArtworkDiscoveryTests(unittest.TestCase):
    def test_mod_jar_preview_image_is_extracted_for_atlas(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            mods = root / "mods"
            mods.mkdir()
            img = root / "pack.png"
            Image.new("RGBA", (16, 16), (44, 180, 230, 255)).save(img)
            jar = mods / "magic-artifacts-1.0.jar"
            with zipfile.ZipFile(jar, "w") as zf:
                zf.write(img, "pack.png")
                zf.writestr("META-INF/mods.toml", 'modLoader="javafml"\nlogoFile="pack.png"\n')

            index = build_pack_content_index(str(root))
            jar_entries = [entry for entry in index["entries"] if entry.get("type") == "mod_jar"]
            self.assertEqual(len(jar_entries), 1)
            image_path = Path(jar_entries[0].get("image_path") or "")
            self.assertTrue(image_path.is_file())
            self.assertIn(".forager", image_path.parts)


if __name__ == "__main__":
    unittest.main()

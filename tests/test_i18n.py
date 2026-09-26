import ast
import unittest
from pathlib import Path
from string import Formatter

from telegram_media_sender.i18n import CATALOG


class TranslationCatalogTests(unittest.TestCase):
    def test_all_literal_interface_keys_have_three_complete_translations(self):
        source = Path(__file__).resolve().parents[1] / "src" / "telegram_media_sender"
        missing = []
        for path in source.glob("*.py"):
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if not isinstance(node, ast.Call) or not node.args:
                    continue
                function = node.func
                translated = (isinstance(function, ast.Name) and function.id == "tr") or (
                    isinstance(function, ast.Attribute) and function.attr == "t")
                if translated and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                    key = node.args[0].value
                    if key not in CATALOG:
                        missing.append(f"{path.name}:{node.lineno}: {key}")
        self.assertEqual(missing, [])

        def fields(value):
            return {name for _literal, name, _format, _conversion in Formatter().parse(value) if name}

        for key, translations in CATALOG.items():
            self.assertEqual(len(translations), 3, key)
            for translation in translations:
                self.assertTrue(translation.strip(), key)
                self.assertEqual(fields(key), fields(translation), key)


if __name__ == "__main__":
    unittest.main()

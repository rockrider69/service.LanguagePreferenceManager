import os
import unittest
import xml.etree.ElementTree as ET


ROOT = os.path.join(os.path.dirname(__file__), "..")


class SettingsOrderingTests(unittest.TestCase):
    def test_variants_are_grouped_in_every_language_spinner(self):
        root = ET.parse(os.path.join(ROOT, "resources", "settings.xml")).getroot()
        expected_groups = (
            ("30207", "30358", "30359"),
            ("30212", "30352", "30351"),
            ("30216", "30353", "30354"),
            ("30233", "30234", "30357"),
            ("30240", "30355", "30356"),
        )
        spinners_checked = 0

        for setting in root.findall(".//setting"):
            labels = [option.get("label") for option in setting.findall("./constraints/options/option")]
            if "30216" not in labels:
                continue
            spinners_checked += 1
            for group in expected_groups:
                start = labels.index(group[0])
                self.assertEqual(list(group), labels[start:start + len(group)],
                                 "Incorrect order in setting " + setting.get("id", ""))

        self.assertEqual(12, spinners_checked)


if __name__ == "__main__":
    unittest.main()

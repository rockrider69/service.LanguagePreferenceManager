import os
import re
import unittest
import xml.etree.ElementTree as ET


ROOT = os.path.join(os.path.dirname(__file__), "..")
BASE_BEFORE_VARIANTS = (
    ("30207", ("30258", "30259")),                                  # Chinese
    ("30212", ("30251", "30252", "30253", "30260", "30261")),        # English
    ("30216", ("30267", "30256", "30264", "30265")),                 # French
    ("30233", ("30257",)),                                           # Portuguese (then Brazil)
    ("30240", ("30254", "30255")),                                   # Spanish
)


def language_spinners():
    root = ET.parse(os.path.join(ROOT, "resources", "settings.xml")).getroot()
    for setting in root.findall(".//setting"):
        labels = [option.get("label") for option in setting.findall("./constraints/options/option")]
        if "30216" in labels:
            yield setting.get("id", ""), setting.findall("./constraints/options/option")


class SettingsOrderingTests(unittest.TestCase):
    def test_there_are_language_spinners(self):
        self.assertGreater(len(list(language_spinners())), 10)

    def test_variants_are_grouped_under_their_language_in_every_spinner(self):
        for setting_id, options in language_spinners():
            labels = [option.get("label") for option in options]
            for base, variants in BASE_BEFORE_VARIANTS:
                start = labels.index(base)
                self.assertEqual(list(variants), labels[start + 1:start + 1 + len(variants)],
                                 "Incorrect order in setting " + setting_id)

    def test_values_and_labels_are_unique_in_every_spinner(self):
        for setting_id, options in language_spinners():
            values = [option.text for option in options]
            labels = [option.get("label") for option in options]
            self.assertEqual(len(values), len(set(values)), "duplicate value in " + setting_id)
            self.assertEqual(len(labels), len(set(labels)), "duplicate label in " + setting_id)

    def test_every_spinner_offers_the_same_languages(self):
        sets = {frozenset(option.get("label") for option in options)
                for _setting_id, options in language_spinners()}
        # spinners differ only by the special entries (None, Any, Undefined, Unknown, Original)
        core = [s - {"30200", "30300", "30350", "30400", "30500"} for s in sets]
        self.assertEqual(1, len(set(core)))


class TranslationTests(unittest.TestCase):
    def test_every_settings_label_is_defined_in_english(self):
        with open(os.path.join(ROOT, "resources", "settings.xml"), encoding="utf-8") as f:
            used = set(re.findall(r'label="(3\d{4})"', f.read()))
        with open(os.path.join(ROOT, "resources", "language", "resource.language.en_gb", "strings.po"),
                  encoding="utf-8") as f:
            defined = set(re.findall(r'msgctxt "#(\d+)"', f.read()))
        self.assertEqual(set(), used - defined)


if __name__ == "__main__":
    unittest.main()

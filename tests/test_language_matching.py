import os
import sys
import unittest


sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "resources", "lib"))

from language_matching import language_match_score


class LanguageMatchingTests(unittest.TestCase):
    def score(self, preference, language="fre", title=""):
        return language_match_score(preference, preference, language, title)

    def test_real_amazon_track_titles_are_distinguished(self):
        self.assertGreater(
            self.score("fr-fr", title="Français (France)"),
            self.score("fr-fr", title="Français (Canada)"),
        )
        self.assertEqual(0, self.score("fr-fr", title="Français (Canada)"))

    def test_real_amazon_order_selects_france_not_first_canadian_track(self):
        streams = (
            {"index": 15, "language": "fre", "name": "Français (Canada)"},
            {"index": 16, "language": "fre", "name": "Français (France)"},
        )
        ranked = [
            (language_match_score("French (France)", "fr-fr",
                                  stream["language"], stream["name"]), stream["index"])
            for stream in streams
        ]
        self.assertEqual(16, max(ranked)[1])

    def test_canadian_aliases(self):
        for title in (
            "French (Canada)", "French Canadian", "Français canadien",
            "Français québécois", "French [CA]", "French VFQ", "fr_CA",
        ):
            with self.subTest(title=title):
                self.assertEqual(300, self.score("fr-ca", title=title))
                self.assertEqual(0, self.score("fr-fr", title=title))

    def test_france_aliases(self):
        for title in (
            "French (France)", "Français de France", "European French",
            "French [FR]", "French VFF", "TRUEFRENCH", "fra-FRA",
        ):
            with self.subTest(title=title):
                self.assertEqual(300, self.score("fr-fr", title=title))
                self.assertEqual(0, self.score("fr-ca", title=title))

    def test_bcp47_language_field_has_priority(self):
        self.assertEqual(300, self.score("fr-ca", "fr-CA", "Français (France)"))
        self.assertEqual(0, self.score("fr-fr", "fr-CA", "Français (France)"))

    def test_unknown_region_is_a_regional_fallback(self):
        self.assertEqual(200, self.score("fr-fr", title="French"))

    def test_generic_french_keeps_legacy_behaviour(self):
        self.assertEqual(100, self.score("fre", title="Français (Canada)"))
        self.assertEqual(100, self.score("fre", title="Français (France)"))

    def test_non_french_matching_is_unchanged(self):
        self.assertEqual(100, language_match_score("English", "eng", "eng", "English (US)"))
        self.assertEqual(0, language_match_score("English", "eng", "ger", "Deutsch"))

    def test_other_real_amazon_duplicates_are_distinguished(self):
        cases = (
            ("es-419", "spa", "Español (Latinoamérica)"),
            ("es-es", "spa", "Español (España)"),
            ("pt-br", "por", "Português (Brasil)"),
            ("pt-pt", "por", "Português (Portugal)"),
            ("zh-hans", "chi", "中文（简体）"),
            ("zh-hant", "chi", "中文（繁體）"),
        )
        for preference, language, title in cases:
            with self.subTest(preference=preference, title=title):
                self.assertEqual(300, self.score(preference, language, title))

    def test_conflicting_variant_does_not_match(self):
        cases = (
            ("es-es", "spa", "Español (Latinoamérica)"),
            ("pt-pt", "por", "Português (Brasil)"),
            ("zh-hans", "chi", "中文（繁體）"),
        )
        for preference, language, title in cases:
            with self.subTest(preference=preference, title=title):
                self.assertEqual(0, self.score(preference, language, title))

    def test_settings_multicode_list_cannot_bypass_specific_region(self):
        self.assertEqual(0, language_match_score("French (France)", "fr,fr-fr", "fr-ca"))
        self.assertEqual(300, language_match_score("French (France)", "fr,fr-fr", "fr-fr"))
        self.assertEqual(200, language_match_score("French (France)", "fr,fr-fr", "fra"))

    def test_generic_multicode_aliases_match_equally(self):
        for code in ("de", "ger", "deu"):
            self.assertEqual(100, language_match_score("German", "de,ger,deu", code))
        self.assertEqual(100, language_match_score("French", "fr,fre,fra", "fra"))

    def test_brazilian_legacy_code_and_settings_name_keep_specificity(self):
        self.assertEqual(300, language_match_score("Portuguese (Brazil)", "pb,pt-br", "pb", "Brazil"))
        self.assertEqual(0, language_match_score("Portuguese (Brazil)", "pb,pt-br", "pt-pt"))


if __name__ == "__main__":
    unittest.main()

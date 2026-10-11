import os
import sys
import unittest


sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "resources", "lib"))

import langutils
from langcodes import languageTranslate


class RegionalLanguageCodeTests(unittest.TestCase):
    def test_settings_values_translate_to_variant_codes(self):
        expected = {
            "53": "en-GB", "54": "en-US", "55": "en-AU", "56": "es-ES", "57": "es-419",
            "58": "fr-CA", "59": "pt-PT", "60": "zh-Hans", "61": "zh-Hant", "69": "fr-FR",
        }
        for setting_value, variant in expected.items():
            with self.subTest(setting_value=setting_value):
                self.assertEqual(variant, languageTranslate(setting_value, 4, 3))

    def test_custom_variant_codes_translate_to_names(self):
        self.assertEqual("French (France)", languageTranslate("fr-FR", 3, 0))
        self.assertEqual("Spanish (Latin America)", languageTranslate("es-419", 3, 0))

    def test_custom_bcp47_aliases_keep_the_variant(self):
        for code, expected in (("fr-fr", "fre-FR"), ("FR_CA", "fre-CA"), ("es-mx", "spa-419"),
                               ("zh-TW", "chi-Hant"), ("pt-br", "pob"), ("en-uk", "eng-GB")):
            with self.subTest(code=code):
                self.assertEqual(expected, langutils.canonical_tag(code))


class VariantMatchTests(unittest.TestCase):
    @staticmethod
    def stream(language, name=""):
        return {"language": language, "name": name}

    def test_exact_region_beats_unlabelled_beats_other_region(self):
        pref = "fr-FR"
        exact = langutils.match_score(pref, self.stream("fre", "Français (France)"))
        unlabelled = langutils.match_score(pref, self.stream("fre", "French"))
        other = langutils.match_score(pref, self.stream("fre", "Français (Canada)"))
        self.assertGreater(exact, unlabelled)
        self.assertGreater(unlabelled, other)
        self.assertEqual(0, other)

    def test_generic_preference_matches_every_variant(self):
        for name in ("Français (France)", "Français (Canada)", "French"):
            with self.subTest(name=name):
                self.assertGreater(langutils.match_score("fre", self.stream("fre", name)), 0)

    def test_two_and_three_letter_codes_are_the_same_language(self):
        self.assertGreater(langutils.match_score("de", self.stream("ger")), 0)
        self.assertGreater(langutils.match_score("deu", self.stream("de")), 0)

    def test_aliases_of_the_1_1_1Beta1_variant_table_are_recognised(self):
        # (preference, stream language, track title or tag) -> must score as an exact region match
        cases = (
            ("fre-CA", "fre", "VFC"), ("fre-CA", "fre", "Française canadienne"), ("fre-CA", "fre", "Québécoise"),
            ("fre-CA", "fre-can", ""), ("fre-FR", "fra-fra", ""), ("fre-FR", "fre-fra", ""),
            ("spa-419", "spa", "Latinoamericana"),
            ("chi-Hans", "chi", "简体中文"), ("chi-Hans", "chi", "簡体"),
            ("chi-Hant", "chi", "繁體中文"), ("chi-Hant", "chi", "繁体"),
            ("eng-US", "eng", "English (United States)"), ("eng-GB", "eng", "English (United Kingdom)"),
        )
        for pref, language, title in cases:
            with self.subTest(pref=pref, language=language, title=title):
                self.assertEqual(2, langutils.match_score(pref, self.stream(language, title)))

    def test_new_aliases_never_select_another_region(self):
        for pref, language, title in (("fre-FR", "fre", "VFC"), ("fre-CA", "fre-fra", ""),
                                      ("eng-GB", "eng", "English (United States)"),
                                      ("chi-Hant", "chi", "简体"), ("spa-ES", "spa", "Latinoamericana")):
            with self.subTest(pref=pref, title=title):
                self.assertEqual(0, langutils.match_score(pref, self.stream(language, title)))

    def test_region_read_from_track_tag(self):
        self.assertGreater(langutils.match_score("pt-BR", self.stream("pt-BR")),
                           langutils.match_score("pt-BR", self.stream("por")))


if __name__ == "__main__":
    unittest.main()

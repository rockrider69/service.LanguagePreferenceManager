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


class SpecialCodeTests(unittest.TestCase):
    def test_untagged_track_with_language_title_is_not_undefined_or_unknown(self):
        for tag in ("", "und", "unk"):
            stream = {"language": tag, "name": "Japanese 5.1"}
            self.assertFalse(langutils.stream_matches_language("und", stream))
            self.assertFalse(langutils.stream_matches_language("unk", stream))
            self.assertTrue(langutils.stream_matches_language("jpn", stream))

    def test_untagged_track_without_language_is_undefined(self):
        stream = {"language": "", "name": "AAC 5.1"}
        self.assertTrue(langutils.stream_matches_language("und", stream))
        self.assertTrue(langutils.stream_matches_language("unk", stream))

    def test_unknown_in_title_of_tagged_track_is_not_unknown(self):
        self.assertFalse(langutils.stream_matches_language("unk", {"language": "fre", "name": "Unknown commentary"}))


class TitleOnlyWhenTagSaysNothingTests(unittest.TestCase):
    def test_a_real_tag_is_never_overridden_by_the_title(self):
        self.assertFalse(langutils.stream_matches_language("eng", {"language": "enm", "name": "English Middle"}))
        self.assertFalse(langutils.stream_matches_language("jpn", {"language": "eng", "name": "Japanese 5.1"}))

    def test_title_names_the_language_when_the_tag_says_nothing(self):
        for tag in ("", "und", "mul"):
            self.assertTrue(langutils.stream_matches_language("jpn", {"language": tag, "name": "Japanese 5.1"}))


class FilenameLanguageTests(unittest.TestCase):
    def read(self, name):
        return langutils.filename_languages(name)

    def test_codes_names_and_markers(self):
        self.assertEqual((["jpn", "ukr"], []), self.read("Movie.2020.1080p.JPN.UKR.mkv"))
        self.assertEqual((["jpn", "ukr"], []), self.read("Anime.Ep01.[Japanese+Ukrainian].mkv"))
        self.assertEqual((["jpn", "ukr"], ["eng"]), self.read("Movie.2020.JPN.UKR.subs.ENG.mkv"))
        self.assertEqual((["jpn", "ukr"], ["eng"]), self.read("Show-JPN-UKR-subs-ENG.mkv"))
        self.assertEqual((["ger"], ["eng", "ita"]), self.read("Movie.Dubbed.German.subs.English.Italian.mkv"))

    def test_regions_and_scripts(self):
        self.assertEqual((["pob", "chi-Hant"], []), self.read("Movie.pt-BR.zh-Hant.mkv"))
        self.assertEqual((["eng-AU", "srp-Latn"], []), self.read("Movie.en-AU.sr-Latn.mkv"))

    def test_common_words_are_not_languages(self):
        self.assertEqual(([], []), self.read("The.Man.In.It.No.He.Is.2020.mkv"))
        self.assertEqual(([], []), self.read("Ice.Age.War.Man.mkv"))
        self.assertEqual(([], []), self.read("NoHints.2021.1080p.x264.mkv"))

    def test_only_the_file_name_is_read(self):
        self.assertEqual((["ger"], []), self.read("smb://nas/Japanese Movies/Film.deu.mkv"))
        self.assertEqual((["fre"], []), self.read("http://h/Film.FRA.mkv?x=ENG|User-Agent=Z"))

    def test_track_numbers_are_not_languages(self):
        self.assertEqual(([], []), self.read("Film.audiostream_2.subtitle_1.mkv"))


if __name__ == "__main__":
    unittest.main()

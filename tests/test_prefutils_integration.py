import os
import sys
import types
import unittest


LIB_PATH = os.path.join(os.path.dirname(__file__), "..", "resources", "lib")
sys.path.insert(0, LIB_PATH)


xbmc = types.ModuleType("xbmc")
xbmc.Player = type("Player", (), {})
xbmc.Monitor = type("Monitor", (), {})
xbmc.sleep = lambda _milliseconds: None
sys.modules["xbmc"] = xbmc

xbmcaddon = types.ModuleType("xbmcaddon")
xbmcaddon.Addon = lambda: types.SimpleNamespace(getSetting=lambda _key: "")
sys.modules["xbmcaddon"] = xbmcaddon

xbmcvfs = types.ModuleType("xbmcvfs")
xbmcvfs.translatePath = lambda path: path
sys.modules["xbmcvfs"] = xbmcvfs

logger = types.ModuleType("logger")
logger.LOG_NONE, logger.LOG_INFO, logger.LOG_DEBUG, logger.LOG_ERROR = range(4)
logger.log = lambda *_args: None
sys.modules["logger"] = logger

custom_preferences = types.ModuleType("custom_media_preference")
custom_preferences.media_preference_manager = types.SimpleNamespace()
custom_preferences.CustomMediaPreference = type("CustomMediaPreference", (), {})
sys.modules["custom_media_preference"] = custom_preferences


class FakeSettings:
    subtitle_keyword_blacklist = []
    subtitle_keyword_blacklist_enabled = False
    audio_keyword_blacklist = []
    audio_keyword_blacklist_enabled = False
    ignore_signs_on = False
    audio_original_preflist_enabled = False
    audio_original_preflist = []
    delay = 0


prefsettings = types.ModuleType("prefsettings")
prefsettings.settings = FakeSettings
sys.modules["prefsettings"] = prefsettings

from prefutils import LangPrefMan_Player, settings
from prefparser import PrefParser


class PreferenceEvaluationTests(unittest.TestCase):
    def make_player(self):
        player = object.__new__(LangPrefMan_Player)
        player.selected_sub = {
            "index": 15, "language": "fre", "name": "Français (Canada)",
            "isforced": False,
        }
        player.subtitles = [
            player.selected_sub,
            {"index": 16, "language": "fre", "name": "Français (France)",
             "isforced": False},
        ]
        player.audio_changed = False
        player.selected_audio_stream = {"index": 0, "language": "eng", "name": "English"}
        player.audiostreams = [player.selected_audio_stream]
        player.getDetails = lambda: None
        return player

    def test_subtitle_evaluator_selects_france_from_real_track_order(self):
        player = self.make_player()
        preferences = [(set(), [("French (France)", "fr-fr", "false")])]
        self.assertEqual(16, player.evalSubPrefs(preferences))

    def test_generic_french_preference_keeps_current_track(self):
        player = self.make_player()
        preferences = [(set(), [("French", "fre", "false")])]
        self.assertEqual(-1, player.evalSubPrefs(preferences))

    def tearDown(self):
        settings.subtitle_keyword_blacklist_enabled = False
        settings.subtitle_keyword_blacklist = []
        settings.audio_keyword_blacklist_enabled = False
        settings.audio_keyword_blacklist = []
        settings.ignore_signs_on = False
        settings.audio_original_preflist_enabled = False
        settings.audio_original_preflist = []

    def test_settings_region_does_not_match_other_region(self):
        player = self.make_player()
        player.subtitles = [player.selected_sub]
        prefs = [(set(), [("French (France)", "fr,fr-fr", "false")])]
        self.assertEqual(-2, player.evalSubPrefs(prefs))

    def test_exact_variant_ranks_above_current_unlabelled_track(self):
        player = self.make_player()
        player.selected_sub["name"] = "French"
        prefs = [(set(), [("French (France)", "fr,fr-fr", "false")])]
        self.assertEqual(16, player.evalSubPrefs(prefs))

    def test_blacklisted_exact_variant_falls_back_to_unlabelled_track(self):
        player = self.make_player()
        player.selected_sub["name"] = "French"
        settings.subtitle_keyword_blacklist_enabled = True
        settings.subtitle_keyword_blacklist = ["france"]
        prefs = [(set(), [("French (France)", "fr,fr-fr", "false")])]
        self.assertEqual(-1, player.evalSubPrefs(prefs))

    def test_audio_uses_same_ranking_and_keeps_best_current_track(self):
        player = self.make_player()
        player.audiostreams = player.subtitles
        player.selected_audio_stream = player.audiostreams[0]
        prefs = [(set(), [("French (France)", "fr,fr-fr")])]
        self.assertEqual(16, player.evalAudioPrefs(prefs))
        player.selected_audio_stream = player.audiostreams[1]
        self.assertEqual(-1, player.evalAudioPrefs(prefs))
        settings.audio_keyword_blacklist_enabled = True
        settings.audio_keyword_blacklist = ["france"]
        self.assertEqual(-2, player.evalAudioPrefs(prefs))

    def test_generic_audio_aliases_keep_current_equivalent_code(self):
        player = self.make_player()
        player.selected_audio_stream = {"index": 1, "language": "deu", "name": "German"}
        player.audiostreams = [{"index": 0, "language": "ger", "name": "German"},
                              player.selected_audio_stream]
        self.assertEqual(-1, player.evalAudioPrefs([(set(), [("German", "de,ger,deu")])]))

    def test_conditional_custom_rule_ranks_variants(self):
        player = self.make_player()
        prefs = PrefParser().parsePrefString("any:fr-fr>any:eng")
        self.assertEqual(16, player.evalCondSubPrefs(prefs))
        player.selected_sub = player.subtitles[1]
        self.assertEqual(16, player.evalCondSubPrefs(prefs))

    def test_conditional_region_applies_only_to_matching_audio(self):
        player = self.make_player()
        player.selected_audio_stream = {"index": 0, "language": "fr-ca", "name": "French"}
        prefs = [(set(), [("French (France)", "fr,fr-fr", "English", "en,eng", "false", "false")])]
        self.assertEqual(-2, player.evalCondSubPrefs(prefs))

    def test_conditional_none_and_forced_subtitle_override(self):
        player = self.make_player()
        player.selected_audio_stream = {"index": 0, "language": "fr-fr", "name": "French"}
        prefs = PrefParser().parsePrefString("fr-fr:non")
        self.assertEqual(-1, player.evalCondSubPrefs(prefs))
        player.subtitles[1]["isforced"] = True
        self.assertEqual(16, player.evalCondSubPrefs(prefs))

    def test_forced_and_signs_filters_are_preserved(self):
        player = self.make_player()
        player.subtitles[1]["isforced"] = True
        self.assertEqual(-2, player.evalSubPrefs([(set(), [("French (France)", "fr-fr", "false")])]))
        self.assertEqual(16, player.evalSubPrefs([(set(), [("French (France)", "fr-fr", "true")])]))
        player.subtitles[1]["isforced"] = False
        player.subtitles[1]["name"] += " Signs"
        settings.ignore_signs_on = True
        self.assertEqual(-2, player.evalSubPrefs([(set(), [("French (France)", "fr-fr", "false")])]))
        self.assertEqual(16, player.evalCondSubPrefs(PrefParser().parsePrefString("any:fr-fr-ss")))

    def test_suffix_removal_preserves_bcp47_codes_ending_in_s(self):
        rule = PrefParser().parsePrefString("any:en-us-ss")[0][1][0]
        self.assertEqual("en-us", rule[3])
        self.assertEqual("true", rule[5])

    def test_original_audio_blacklist_still_applies(self):
        player = self.make_player()
        player.audiostreams += [
            {"index": 1, "language": "eng", "name": "Commentary", "isoriginal": True},
            {"index": 2, "language": "eng", "name": "Original", "isoriginal": True}]
        settings.audio_original_preflist_enabled = True
        settings.audio_original_preflist = ["any", "any"]
        settings.audio_keyword_blacklist_enabled = True
        settings.audio_keyword_blacklist = ["commentary"]
        self.assertEqual(2, player.evalAudioPrefs([]))


if __name__ == "__main__":
    unittest.main()

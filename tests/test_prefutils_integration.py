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
xbmc.getLocalizedString = lambda _id: "(External)"
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
    audio_original_any = False
    sub_format_order = []
    audio_original_langs = []
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
        player.getDetails = lambda: True
        player.genres_and_tags = set()
        return player

    def test_subtitle_evaluator_selects_france_from_real_track_order(self):
        player = self.make_player()
        preferences = [(set(), [("French (France)", "fr-FR", "false")])]
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
        settings.audio_original_any = False
        settings.audio_original_langs = []
        settings.sub_format_order = []

    def test_settings_region_does_not_match_other_region(self):
        player = self.make_player()
        player.subtitles = [player.selected_sub]
        prefs = [(set(), [("French (France)", "fr-FR", "false")])]
        self.assertEqual(-2, player.evalSubPrefs(prefs))

    def test_exact_variant_ranks_above_current_unlabelled_track(self):
        player = self.make_player()
        player.selected_sub["name"] = "French"
        prefs = [(set(), [("French (France)", "fr-FR", "false")])]
        self.assertEqual(16, player.evalSubPrefs(prefs))

    def test_blacklisted_exact_variant_falls_back_to_unlabelled_track(self):
        player = self.make_player()
        player.selected_sub["name"] = "French"
        settings.subtitle_keyword_blacklist_enabled = True
        settings.subtitle_keyword_blacklist = ["france"]
        prefs = [(set(), [("French (France)", "fr-FR", "false")])]
        self.assertEqual(-1, player.evalSubPrefs(prefs))

    def test_audio_uses_same_ranking_and_keeps_best_current_track(self):
        player = self.make_player()
        player.audiostreams = player.subtitles
        player.selected_audio_stream = player.audiostreams[0]
        prefs = [(set(), [("French (France)", "fr-FR")])]
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
        prefs = [(set(), [("French (France)", "fr-FR", "English", "en,eng", "false", "false")])]
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
        self.assertEqual(-2, player.evalSubPrefs([(set(), [("French (France)", "fr-FR", "false")])]))
        self.assertEqual(16, player.evalSubPrefs([(set(), [("French (France)", "fr-fr", "true")])]))
        player.subtitles[1]["isforced"] = False
        player.subtitles[1]["name"] += " Signs"
        settings.ignore_signs_on = True
        self.assertEqual(-2, player.evalSubPrefs([(set(), [("French (France)", "fr-FR", "false")])]))
        # the -ss tag selects Signs&Songs tracks, but the ignore toggle always wins
        self.assertEqual(-2, player.evalCondSubPrefs(PrefParser().parsePrefString("any:fr-fr-ss")))
        settings.ignore_signs_on = False
        self.assertEqual(16, player.evalCondSubPrefs(PrefParser().parsePrefString("any:fr-fr-ss")))

    def test_suffix_removal_preserves_bcp47_codes_ending_in_s(self):
        rule = PrefParser().parsePrefString("any:en-us-ss")[0][1][0]
        self.assertEqual("eng-US", rule[3])
        self.assertEqual("true", rule[5])

    def test_original_audio_blacklist_still_applies(self):
        player = self.make_player()
        player.audiostreams += [
            {"index": 1, "language": "eng", "name": "Commentary", "isoriginal": True},
            {"index": 2, "language": "eng", "name": "Original", "isoriginal": True}]
        settings.audio_original_preflist_enabled = True
        settings.audio_original_any = True
        settings.audio_original_preflist = ["any", "any"]
        settings.audio_keyword_blacklist_enabled = True
        settings.audio_keyword_blacklist = ["commentary"]
        self.assertEqual(2, player.evalAudioPrefs([]))


    # ---- subtitle format preference (settings SubFormat1..3) -------------------------------------------------
    def english_subs(self, formats):
        """Three English subtitle tracks (indexes 0, 1, 2) whose known formats are given as {index: format}."""
        player = self.make_player()
        player.subtitles = [{"index": i, "language": "eng", "name": "English", "isforced": False} for i in range(3)]
        player.selected_sub = player.subtitles[0]
        player.subtitle_formats = lambda: formats
        return player

    def test_without_a_format_order_the_first_matching_track_stays(self):
        player = self.english_subs({0: "pgs", 1: "srt", 2: "ass"})
        self.assertEqual(-1, player.evalSubPrefs([(set(), [("English", "eng", "false")])]))

    def test_best_format_is_taken_and_replaces_the_current_track(self):
        settings.sub_format_order = ["srt", "ass"]
        player = self.english_subs({0: "pgs", 1: "ass", 2: "srt"})
        self.assertEqual(2, player.evalSubPrefs([(set(), [("English", "eng", "false")])]))

    def test_current_track_in_the_best_format_is_kept(self):
        settings.sub_format_order = ["ass", "srt"]
        player = self.english_subs({0: "ass", 1: "srt", 2: "ass"})
        self.assertEqual(-1, player.evalSubPrefs([(set(), [("English", "eng", "false")])]))

    def test_second_format_is_used_when_the_first_is_missing(self):
        settings.sub_format_order = ["pgs", "srt", "ass"]
        player = self.english_subs({0: "ass", 1: "vobsub", 2: "srt"})
        self.assertEqual(2, player.evalSubPrefs([(set(), [("English", "eng", "false")])]))

    def test_unlisted_and_unknown_formats_rank_after_the_listed_ones(self):
        settings.sub_format_order = ["srt"]
        player = self.english_subs({0: "pgs", 2: "srt"})            # track 1 has no known format
        self.assertEqual(2, player.evalSubPrefs([(set(), [("English", "eng", "false")])]))

    def test_unknown_formats_change_nothing(self):
        settings.sub_format_order = ["srt", "ass"]
        player = self.english_subs({})
        self.assertEqual(-1, player.evalSubPrefs([(set(), [("English", "eng", "false")])]))

    def test_the_language_always_wins_over_the_format(self):
        settings.sub_format_order = ["srt"]
        player = self.english_subs({0: "srt", 1: "srt", 2: "ass"})
        player.subtitles[2]["language"] = "fre"
        player.subtitles[2]["name"] = "Francais"
        self.assertEqual(2, player.evalSubPrefs([(set(), [("French", "fre", "false")])]))

    def test_conditional_rules_use_the_format_order(self):
        settings.sub_format_order = ["srt", "ass"]
        player = self.english_subs({0: "ass", 1: "srt", 2: "ass"})
        player.selected_audio_stream = {"index": 0, "language": "jpn", "name": "Japanese"}
        prefs = PrefParser().parsePrefString("jpn:eng")
        self.assertEqual(1, player.evalCondSubPrefs(prefs))

    def test_a_format_word_in_the_title_is_read_when_the_file_is_unreadable(self):
        player = self.make_player()
        player.subtitles = [{"index": 0, "language": "eng", "name": "English [PGS]", "isforced": False},
                            {"index": 1, "language": "eng", "name": "English (SRT)", "isforced": False},
                            {"index": 2, "language": "eng", "name": "English", "isforced": False}]
        player.selected_sub = player.subtitles[0]
        player.getPlayingFile = lambda: "/video/movie.mp4"          # not Matroska: no codecs
        player.embedded_subtitle_codecs = lambda: None
        player.sub_formats = (None, {})
        settings.sub_format_order = ["srt", "pgs"]
        self.assertEqual({0: "pgs", 1: "srt"}, player.subtitle_formats())
        self.assertEqual(1, player.evalSubPrefs([(set(), [("English", "eng", "false")])]))

    def test_formats_of_embedded_tracks_come_from_the_file_in_kodi_order(self):
        player = self.make_player()
        player.subtitles = [{"index": 0, "language": "en", "name": "(External)", "isforced": False},
                            {"index": 1, "language": "en", "name": "English", "isforced": False},
                            {"index": 2, "language": "en", "name": "English", "isforced": False},
                            {"index": 3, "language": "fr", "name": "Francais", "isforced": False}]
        player.getPlayingFile = lambda: "/video/movie.mkv"
        player.embedded_subtitle_codecs = lambda: ["S_TEXT/UTF8", "S_HDMV/PGS", "S_TEXT/ASS"]
        player.subtitle_file_tags = lambda externals: [{"tag": "en", "words": ["en"], "ext": ".ass"}]
        player.sub_formats = (None, {})
        self.assertEqual({0: "ass", 1: "srt", 2: "pgs", 3: "ass"}, player.subtitle_formats())

    def test_an_external_file_of_an_uncertain_format_is_unknown(self):
        player = self.make_player()
        player.subtitles = [{"index": 0, "language": "en", "name": "(External)", "isforced": False},
                            {"index": 1, "language": "en", "name": "(External)", "isforced": False}]
        player.getPlayingFile = lambda: "/video/movie.mkv"
        player.embedded_subtitle_codecs = lambda: None
        # Movie.en.srt and Movie.en.ass: two streams, the same language, no telling which is which
        player.subtitle_file_tags = lambda externals: [{"tag": "en", "words": ["en"], "ext": ".srt"},
                                                       {"tag": "en", "words": ["en"], "ext": ".ass"}]
        player.sub_formats = (None, {})
        self.assertEqual({}, player.subtitle_formats())


if __name__ == "__main__":
    unittest.main()

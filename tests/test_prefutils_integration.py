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


class ForcedDefaultRegexTests(unittest.TestCase):
    """Regex filter / fallback must not play a forced (or default-flagged forced) track unless the conditional
    subtitle rules ask for it."""

    def setUp(self):
        import re
        xbmc.getLocalizedString = lambda _id: "(External)"
        settings.regex_sub_filter_enabled = True
        settings.regex_sub_filter = re.compile(r'(?i:forced|signs?|songs?)')
        settings.regex_sub_exclusion = None
        settings.condsub_prefs_on = True
        settings.turn_subs_on = True
        settings.turn_subs_off = False
        self.player = object.__new__(LangPrefMan_Player)
        self.player.getPlayingFile = lambda: (_ for _ in ()).throw(RuntimeError())
        self.player.sub_codecs = (None, None)
        self.player.subtitles = [
            {"index": 0, "language": "eng", "name": "English Forced", "isforced": True, "isdefault": True},
            {"index": 1, "language": "jpn", "name": "Japanese Forced", "isforced": True, "isdefault": False},
            {"index": 2, "language": "eng", "name": "English", "isforced": False, "isdefault": False},
            {"index": 3, "language": "eng", "name": "Signs & Songs", "isforced": False, "isdefault": False},
        ]

    def tearDown(self):
        for key in ("regex_sub_filter_enabled", "regex_sub_filter", "regex_sub_exclusion", "condsub_prefs_on",
                    "turn_subs_on", "turn_subs_off"):
            if hasattr(FakeSettings, key):
                delattr(FakeSettings, key)

    def test_regex_prefers_signs_over_forced_track(self):
        self.assertEqual(3, self.player.evalRegexSubPrefs())

    def test_regex_forced_only_hit_defers_to_conditionals(self):
        del self.player.subtitles[3]
        self.assertEqual(-2, self.player.evalRegexSubPrefs())

    def test_regex_forced_only_hit_kept_without_conditionals(self):
        del self.player.subtitles[3]
        settings.condsub_prefs_on = False
        self.assertEqual(0, self.player.evalRegexSubPrefs())

    def test_fallback_skips_default_forced_track(self):
        self.assertEqual(2, self.player.evalFallbackSubPrefs())

    def test_fallback_still_uses_non_forced_default(self):
        self.player.subtitles[3]["isdefault"] = True
        self.assertEqual(3, self.player.evalFallbackSubPrefs())

    def test_fallback_with_only_forced_tracks_selects_nothing(self):
        self.player.subtitles = self.player.subtitles[:2]
        self.assertEqual(-2, self.player.evalFallbackSubPrefs())


class AudioOrderTests(unittest.TestCase):
    """The audio preference order and the conditional rules' audio part are honored whatever flags the tracks carry
    (Kodi starts on the default-flagged audio track, which says nothing about the user's order)."""

    def setUp(self):
        self.player = object.__new__(LangPrefMan_Player)
        self.player.audiostreams = [
            {"index": 0, "language": "eng", "name": "English", "isdefault": True, "isforced": True},
            {"index": 1, "language": "jpn", "name": "Japanese", "isdefault": False, "isforced": False},
            {"index": 2, "language": "fre", "name": "French", "isdefault": False, "isforced": False},
        ]
        self.player.selected_audio_stream = self.player.audiostreams[0]
        self.player.subtitles = [
            {"index": 0, "language": "eng", "name": "English", "isforced": False},
            {"index": 1, "language": "fre", "name": "French", "isforced": False},
            {"index": 2, "language": "ger", "name": "German", "isforced": False},
        ]
        self.player.selected_sub = self.player.subtitles[2]
        self.player.audio_changed = False
        self.player.getDetails = lambda: True
        self.player.genres_and_tags = set()
        self.player.LPM_initial_run_done = False
        self.player.lpm_audio_target = None

    def test_audio_order_beats_default_and_forced_flag(self):
        prefs = PrefParser().parsePrefString("jpn>eng")
        self.assertEqual(1, self.player.evalAudioPrefs(prefs))
        prefs = PrefParser().parsePrefString("eng>jpn")
        self.assertEqual(-1, self.player.evalAudioPrefs(prefs))

    def test_conditional_rules_follow_rule_order_for_the_selected_audio(self):
        self.player.selected_audio_stream = self.player.audiostreams[1]
        self.assertEqual(0, self.player.evalCondSubPrefs(PrefParser().parsePrefString("jpn:eng>any:fre")))
        self.assertEqual(1, self.player.evalCondSubPrefs(PrefParser().parsePrefString("any:fre>jpn:eng")))

    def test_initial_run_uses_the_audio_track_lpm_switched_to(self):
        # Kodi still reports the default-flagged English audio, LPM has just switched to Japanese (index 1)
        self.player.lpm_audio_target = 1
        prefs = PrefParser().parsePrefString("jpn:eng>eng:fre")
        self.assertEqual(0, self.player.evalCondSubPrefs(prefs))

    def test_pending_target_is_ignored_after_the_initial_run(self):
        self.player.lpm_audio_target = 1
        self.player.LPM_initial_run_done = True
        prefs = PrefParser().parsePrefString("jpn:eng>eng:fre")
        self.assertEqual(1, self.player.evalCondSubPrefs(prefs))



class CondAudioTests(unittest.TestCase):
    def player(self, current):
        player = object.__new__(LangPrefMan_Player)
        player.audiostreams = [
            {"index": 0, "language": "jpn", "name": "Japanese"},
            {"index": 1, "language": "ukr", "name": "Ukrainian"},
            {"index": 2, "language": "ukr", "name": "Ukrainian"},
        ]
        player.selected_audio_stream = player.audiostreams[current]
        player.getDetails = lambda: True
        player.genres_and_tags = set()
        return player

    RULES = [(set(), [("Italian", "ita", "English", "eng", "false", "false"),
                      ("Japanese", "jpn", "English", "eng", "true", "false"),
                      ("Ukrainian", "ukr", "English", "eng", "false", "false"),
                      ("Any", "any", "None", "non", "false", "false")])]

    def test_first_rule_with_available_audio_wins_over_kodi_default(self):
        self.assertEqual(0, self.player(1).evalCondAudioPrefs(self.RULES))

    def test_playing_track_already_matching_is_kept(self):
        self.assertEqual(-1, self.player(0).evalCondAudioPrefs(self.RULES))

    def test_rule_order_decides(self):
        rules = [(set(), [self.RULES[0][1][2], self.RULES[0][1][1]])]
        self.assertEqual(1, self.player(0).evalCondAudioPrefs(rules))

    def test_no_available_audio(self):
        rules = [(set(), [self.RULES[0][1][0], ("None", "non", "English", "eng", "false", "false")])]
        self.assertEqual(-2, self.player(1).evalCondAudioPrefs(rules))


class FilenameEvaluationTests(unittest.TestCase):
    AUDIO = [{"index": 0, "language": "ukr", "name": "Ukrainian"}, {"index": 1, "language": "jpn", "name": "Japanese"},
             {"index": 2, "language": "pt-BR", "name": "Portuguese (Brazil)"}]
    SUBS = [{"index": 0, "language": "eng", "name": "English", "isforced": False},
            {"index": 1, "language": "jpn", "name": "Japanese", "isforced": False}]

    def player(self, filename):
        import re
        settings.reg = re.compile(r"audiostream[_|.|-]*\d+|subtitle[_|.|-]*\d+", re.I)
        settings.split = re.compile(r"[_|.|-]+", re.I)
        player = object.__new__(LangPrefMan_Player)
        player.audiostreams, player.subtitles = self.AUDIO, self.SUBS
        player.getPlayingFile = lambda: filename
        return player

    def test_track_numbers_still_win(self):
        self.assertEqual((2, 1), self.player("Movie.JPN.audiostream_2.subtitle_1.mkv").evalFilenamePrefs())

    def test_languages_of_the_name(self):
        self.assertEqual((1, 1), self.player("Movie.JPN.UKR.subs.JPN.mkv").evalFilenamePrefs())
        self.assertEqual((2, 0), self.player("Movie.pt-BR.subs.eng.mkv").evalFilenamePrefs())

    def test_a_language_without_a_track_falls_to_the_next_one(self):
        self.assertEqual((0, 0), self.player("Movie.FRA.UKR.mkv").evalFilenamePrefs())

    def test_nothing_usable_selects_the_first_tracks(self):
        self.assertEqual((0, 0), self.player("Movie.2021.1080p.mkv").evalFilenamePrefs())
        self.assertEqual((0, 0), self.player("Movie.FRA.subs.GER.mkv").evalFilenamePrefs())


if __name__ == "__main__":
    unittest.main()

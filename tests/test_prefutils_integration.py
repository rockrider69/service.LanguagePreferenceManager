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
    sub_format_slots = [None, None, None]
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
        settings.sub_format_slots = [None, None, None]

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

    def _original_player(self, sub_name, flag=False, forced=False, audio_original=False):
        player = self.make_player()
        player.selected_audio_stream = {"index": 0, "language": "eng", "name": "English", "isoriginal": audio_original}
        player.audiostreams = [player.selected_audio_stream]
        player.subtitles = [
            {"index": 0, "language": "eng", "name": "English", "isforced": False},
            {"index": 1, "language": "fre", "name": sub_name, "isforced": forced, "isoriginal": flag},
        ]
        player.selected_sub = player.subtitles[0]
        player.getSelectedSubtitleIndex = lambda: 0
        return player

    def test_conditional_original_subtitle_matches_a_title_saying_original(self):
        # "original" in the subtitle title is enough (Kodi reports no original flag for subtitles)
        player = self._original_player("French original")
        self.assertEqual(1, player.evalCondSubPrefs(PrefParser().parsePrefString("eng:org")))

    def test_conditional_original_subtitle_ignores_a_flag_without_title(self):
        player = self._original_player("French", flag=True)
        self.assertEqual(-2, player.evalCondSubPrefs(PrefParser().parsePrefString("eng:org")))

    def test_conditional_original_subtitle_title_in_a_forced_track_is_not_taken_by_a_non_forced_rule(self):
        player = self._original_player("French original", forced=True)
        self.assertEqual(-2, player.evalCondSubPrefs(PrefParser().parsePrefString("eng:org")))

    def test_conditional_original_audio_needs_the_flag_not_the_title(self):
        player = self._original_player("French")
        player.selected_audio_stream["name"] = "English original"
        self.assertEqual(-2, player.evalCondSubPrefs(PrefParser().parsePrefString("org:fre")))
        player.selected_audio_stream["isoriginal"] = True
        self.assertEqual(1, player.evalCondSubPrefs(PrefParser().parsePrefString("org:fre")))

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

    def cond_player(self):
        settings.sub_format_order = ["srt", "ass", "pgs"]
        settings.sub_format_slots = ["srt", "ass", "pgs"]
        player = self.english_subs({0: "ass", 1: "srt", 2: "pgs"})
        player.selected_audio_stream = {"index": 0, "language": "jpn", "name": "Japanese"}
        return player

    def cond_rule(self, slot):
        return [(set(), [("Japanese", "jpn", "English", "eng", "false", "false", slot)])]

    def test_a_conditional_rule_without_a_slot_uses_the_general_order(self):
        self.assertEqual(1, self.cond_player().evalCondSubPrefs(self.cond_rule(0)))

    def test_a_conditional_rule_can_use_the_second_or_third_format_first(self):
        self.assertEqual(1, self.cond_player().evalCondSubPrefs(self.cond_rule(1)))
        self.assertEqual(0, self.cond_player().evalCondSubPrefs(self.cond_rule(2)))
        self.assertEqual(2, self.cond_player().evalCondSubPrefs(self.cond_rule(3)))

    def test_a_chosen_format_that_is_missing_falls_back_to_the_general_order(self):
        player = self.cond_player()
        player.subtitle_formats = lambda: {0: "ass", 1: "srt", 2: "vobsub"}
        self.assertEqual(0, player.evalCondSubPrefs(self.cond_rule(2)))
        player.subtitle_formats = lambda: {0: "vobsub", 1: "srt", 2: "ass"}
        self.assertEqual(1, player.evalCondSubPrefs(self.cond_rule(3)))

    def test_an_empty_slot_leaves_the_general_order(self):
        player = self.cond_player()
        settings.sub_format_slots = ["srt", "ass", None]
        self.assertEqual(1, player.evalCondSubPrefs(self.cond_rule(3)))

    def test_old_six_field_rules_still_work(self):
        player = self.cond_player()
        self.assertEqual(1, player.evalCondSubPrefs([(set(), [("Japanese", "jpn", "English", "eng", "false", "false")])]))

    def test_custom_rules_can_name_the_format_slot(self):
        parser = PrefParser()
        rule = parser.parsePrefString("jpn:eng-f2>jpn:eng-f3-ff>jpn:eng-ss-f1>jpn:eng")
        self.assertEqual([2, 3, 1, 0], [r[6] for r in rule[0][1]] if isinstance(rule[0], tuple) else [r[6] for r in rule])
        self.assertEqual(["false", "true", "false", "false"],
                         [r[4] for r in (rule[0][1] if isinstance(rule[0], tuple) else rule)])
        self.assertEqual(["false", "false", "true", "false"],
                         [r[5] for r in (rule[0][1] if isinstance(rule[0], tuple) else rule)])
        self.assertEqual(2, self.cond_player().evalCondSubPrefs(parser.parsePrefString("jpn:eng-f3")))

    def converter_player(self):
        from unittest import mock
        player = self.make_player()
        player.sub_converting = False
        player.sub_convert_pending = False
        player.sub_convert_quiet_until = 0
        settings.sub_converter_on = True
        settings.regex_sub_filter_enabled = False
        settings.condsub_prefs_on = True
        settings.is_store_user_preference_for_player = lambda p: False
        player.getSelectedSubtitleIndex = lambda: 1
        player.getSelectedSubtitleLanguage = lambda: "eng"
        player.selected_sub_enabled = True
        return player, mock

    def test_switching_subtitles_during_playback_starts_the_sub_converter(self):
        player, mock = self.converter_player()
        with mock.patch("prefutils.threading.Thread") as thread:
            player._check_subtitle_change(0, True, "jpn")     # the track was 0, now 1
        thread.assert_called_once()
        self.assertTrue(player.sub_converting)

    def test_no_change_does_not_start_the_sub_converter(self):
        player, mock = self.converter_player()
        with mock.patch("prefutils.threading.Thread") as thread:
            player._check_subtitle_change(1, True, "eng")
        thread.assert_not_called()

    def test_a_switch_during_a_running_conversion_is_converted_afterwards(self):
        player, mock = self.converter_player()
        player.sub_converting = True
        with mock.patch("prefutils.threading.Thread") as thread:
            player._check_subtitle_change(0, True, "jpn")
        thread.assert_not_called()
        self.assertTrue(player.sub_convert_pending)
        player._sub_converter_job = lambda: None               # the next run finds nothing to do
        started = []
        player.start_sub_converter = lambda user_switch=False: started.append(user_switch)
        player.sub_converting = True
        import prefutils
        old_playing = prefutils.kodirpc.is_playing_video
        prefutils.kodirpc.is_playing_video = lambda: True      # asked over JSON-RPC
        try:
            player._sub_converter_run()
        finally:
            prefutils.kodirpc.is_playing_video = old_playing
        self.assertEqual([False], started)
        self.assertFalse(player.sub_convert_pending)
        self.assertFalse(player.sub_converting)

    def test_the_converters_own_switch_is_not_a_user_switch(self):
        import time
        player, mock = self.converter_player()
        player.sub_convert_quiet_until = time.time() + 5
        # what Kodi shows after the converter selected its copy: an external subtitle
        player.selected_sub = {"index": 3, "language": "eng", "name": "Movie [abc123-0].eng.srt (External)"}
        with mock.patch("prefutils.threading.Thread") as thread:
            player._check_subtitle_change(0, True, "jpn")
        thread.assert_not_called()

    def test_another_track_picked_right_after_a_conversion_is_a_user_switch(self):
        import time
        player, mock = self.converter_player()
        player.sub_convert_quiet_until = time.time() + 5
        player.selected_sub = {"index": 2, "language": "ger", "name": "German"}      # an embedded track
        with mock.patch("prefutils.threading.Thread") as thread:
            player._check_subtitle_change(0, True, "jpn")
        thread.assert_called_once()

    def flagged_player(self, formats, flagged, names=None):
        """English tracks 0..n-1 in the given formats; the ones in `flagged` carry only the forced flag."""
        player = self.make_player()
        player.subtitles = [{"index": i, "language": "eng", "name": (names or {}).get(i, "English"),
                             "isforced": i in flagged} for i in range(len(formats))]
        player.selected_sub = player.subtitles[0]
        player.selected_audio_stream = {"index": 0, "language": "jpn", "name": "Japanese"}
        player.subtitle_formats = lambda: dict(enumerate(formats))
        return player

    def cond(self, forced="false"):
        return [(set(), [("Japanese", "jpn", "English", "eng", forced, "false", 0)])]

    def test_a_flagged_ass_track_is_chosen_by_the_format_preference_over_srt(self):
        settings.sub_format_order = ["ass", "srt"]
        settings.sub_format_slots = ["ass", "srt", None]
        player = self.flagged_player(["srt", "ass"], {1})              # the ASS carries "forced + default"
        self.assertEqual(1, player.evalCondSubPrefs(self.cond()))
        settings.sub_format_order = ["srt", "ass"]
        settings.sub_format_slots = ["srt", "ass", None]
        self.assertEqual(0, player.evalCondSubPrefs(self.cond()))      # srt is current and best

    def test_a_flagged_picture_track_stays_a_forced_track(self):
        settings.sub_format_order = ["pgs", "srt"]
        settings.sub_format_slots = ["pgs", "srt", None]
        player = self.flagged_player(["pgs", "srt"], {0})              # forced PGS: foreign parts only
        self.assertEqual(1, player.evalCondSubPrefs(self.cond()))

    def test_a_track_named_forced_is_never_chosen_by_a_rule_that_wants_no_forced(self):
        settings.sub_format_order = ["ass", "srt"]
        settings.sub_format_slots = ["ass", "srt", None]
        player = self.flagged_player(["srt", "ass"], {1}, {1: "English forced"})
        self.assertEqual(0, player.evalCondSubPrefs(self.cond()))      # the srt, already playing

    def test_without_a_format_preference_a_flagged_track_is_still_a_forced_track(self):
        settings.sub_format_order = []
        player = self.flagged_player(["srt", "ass"], {1})
        player.subtitle_formats = lambda: {0: "srt", 1: "ass"}
        self.assertEqual(0, player.evalCondSubPrefs(self.cond()))      # only the srt is eligible

    def test_same_format_the_unflagged_track_comes_first(self):
        settings.sub_format_order = ["ass", "srt"]
        settings.sub_format_slots = ["ass", "srt", None]
        player = self.flagged_player(["ass", "ass"], {0})
        player.selected_sub = player.subtitles[0]
        self.assertEqual(1, player.evalCondSubPrefs(self.cond()))

    def test_a_forced_rule_still_takes_a_flagged_track(self):
        settings.sub_format_order = ["ass", "srt"]
        settings.sub_format_slots = ["ass", "srt", None]
        player = self.flagged_player(["srt", "ass"], {1})
        self.assertEqual(1, player.evalCondSubPrefs(self.cond("true")))      # the forced rule wants the flagged track

    def test_a_format_word_in_the_title_is_read_when_the_file_is_unreadable(self):
        player = self.make_player()
        player.subtitles = [{"index": 0, "language": "eng", "name": "English [PGS]", "isforced": False},
                            {"index": 1, "language": "eng", "name": "English (SRT)", "isforced": False},
                            {"index": 2, "language": "eng", "name": "English", "isforced": False}]
        player.selected_sub = player.subtitles[0]
        player.playing_file = lambda: "/video/movie.mp4"          # not Matroska: no codecs
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
        player.playing_file = lambda: "/video/movie.mkv"
        player.embedded_subtitle_codecs = lambda: ["S_TEXT/UTF8", "S_HDMV/PGS", "S_TEXT/ASS"]
        player.subtitle_file_tags = lambda externals: [{"tag": "en", "words": ["en"], "ext": ".ass"}]
        player.sub_formats = (None, {})
        self.assertEqual({0: "ass", 1: "srt", 2: "pgs", 3: "ass"}, player.subtitle_formats())

    def external_player(self, tags, streams=2, embedded=None):
        player = self.make_player()
        player.subtitles = [{"index": i, "language": "en", "name": "(External)", "isforced": False}
                            for i in range(streams)]
        if embedded:
            player.subtitles.append({"index": streams, "language": "en", "name": "English", "isforced": False})
        player.playing_file = lambda: "/video/movie.mkv"
        player.embedded_subtitle_codecs = lambda: embedded
        player.subtitle_file_tags = lambda externals: tags
        player.sub_formats = (None, {})
        player.sub_format_options = {}
        player.selected_sub = player.subtitles[-1]
        return player

    def test_two_external_files_of_one_language_follow_kodis_reverse_listing_order(self):
        # Movie.en.srt and Movie.en.ass: two streams, the same language and name. Kodi opens the files in the reverse
        # of the folder listing (listing ass, srt -> streams srt, ass)
        tags = [{"tag": "en", "words": ["en"], "ext": ".ass", "dir": "/video"},
                {"tag": "en", "words": ["en"], "ext": ".srt", "dir": "/video"}]
        player = self.external_player(tags)
        self.assertEqual({0: "srt", 1: "ass"}, player.subtitle_formats())

    def test_a_preferred_external_ass_beats_an_embedded_pgs(self):
        tags = [{"tag": "en", "words": ["en"], "ext": ".ass", "dir": "/video"},
                {"tag": "en", "words": ["en"], "ext": ".srt", "dir": "/video"}]
        player = self.external_player(tags, embedded=["S_HDMV/PGS"])
        player.selected_audio_stream = {"index": 0, "language": "jpn", "name": "Japanese"}
        settings.sub_format_order = ["ass", "srt", "pgs"]
        settings.sub_format_slots = ["ass", "srt", "pgs"]
        rule = [(set(), [("Japanese", "jpn", "English", "eng", "false", "false", 0)])]
        self.assertEqual(1, player.evalCondSubPrefs(rule))          # stream 1 = Movie.en.ass
        settings.sub_format_order = ["srt", "ass", "pgs"]
        player.sub_formats = (None, {})
        self.assertEqual(0, player.evalCondSubPrefs(rule))          # stream 0 = Movie.en.srt

    def test_files_from_several_folders_are_not_ordered_but_rank_as_their_best_format(self):
        tags = [{"tag": "en", "words": ["en"], "ext": ".srt", "dir": "/video"},
                {"tag": "en", "words": ["en"], "ext": ".ass", "dir": "/video/Subs"}]
        player = self.external_player(tags, embedded=["S_HDMV/PGS"])
        player.selected_audio_stream = {"index": 0, "language": "jpn", "name": "Japanese"}
        settings.sub_format_order = ["ass", "srt", "pgs"]
        settings.sub_format_slots = ["ass", "srt", "pgs"]
        self.assertEqual({2: "pgs"}, player.subtitle_formats())
        self.assertEqual({0: {"srt", "ass"}, 1: {"srt", "ass"}}, player.sub_format_options)
        rule = [(set(), [("Japanese", "jpn", "English", "eng", "false", "false", 0)])]
        self.assertEqual(0, player.evalCondSubPrefs(rule))          # an external file, never the pgs

    def test_three_files_two_formats_are_matched_in_reverse_listing_order(self):
        tags = [{"tag": "en", "words": ["en"], "ext": ".ass", "dir": "/video"},
                {"tag": "fr", "words": ["fr"], "ext": ".ass", "dir": "/video"},
                {"tag": "en", "words": ["eng"], "ext": ".srt", "dir": "/video"}]
        player = self.make_player()
        player.subtitles = [{"index": 0, "language": "en", "name": "(External)", "isforced": False},
                            {"index": 1, "language": "fr", "name": "(External)", "isforced": False},
                            {"index": 2, "language": "en", "name": "(External)", "isforced": False}]
        player.playing_file = lambda: "/video/movie.mkv"
        player.embedded_subtitle_codecs = lambda: None
        player.subtitle_file_tags = lambda externals: tags
        player.sub_formats = (None, {})
        self.assertEqual({0: "srt", 1: "ass", 2: "ass"}, player.subtitle_formats())


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
        self.player.playing_file = lambda: (_ for _ in ()).throw(RuntimeError())
        self.player.sub_codecs = (None, None)
        self.player.subtitles = [
            {"index": 0, "language": "eng", "name": "English Forced", "isforced": True, "isdefault": True},
            {"index": 1, "language": "jpn", "name": "Japanese Forced", "isforced": True, "isdefault": False},
            {"index": 2, "language": "eng", "name": "English", "isforced": False, "isdefault": False},
            {"index": 3, "language": "eng", "name": "Signs & Songs", "isforced": False, "isdefault": False},
        ]

    def tearDown(self):
        for key in ("regex_sub_filter_enabled", "regex_sub_filter", "regex_sub_exclusion", "condsub_prefs_on",
                    "turn_subs_on", "turn_subs_off", "sub_prefs_on", "custom_sub_prefs_on", "SubtitlePrefs",
                    "sub_format_order"):
            if hasattr(FakeSettings, key):
                delattr(FakeSettings, key)

    def regex_language_setup(self, formats, order):
        import re
        settings.regex_sub_filter = re.compile(r'(?i:signs?|songs?|forced)')
        settings.sub_prefs_on = True
        settings.custom_sub_prefs_on = False
        settings.SubtitlePrefs = [(set(), [("English", "eng")])]
        settings.condsub_prefs_on = False
        settings.sub_format_order = order
        self.player.subtitles = [
            {"index": 0, "language": "jpn", "name": "Signs & Songs", "isforced": False},
            {"index": 1, "language": "eng", "name": "Signs & Songs", "isforced": False},
            {"index": 2, "language": "eng", "name": "Signs & Songs", "isforced": True},
        ]
        self.player.subtitle_formats = lambda: formats
        self.player.genres_and_tags = set()
        self.player.cond_audio_stream = lambda: None

    def test_regex_uses_preferred_language_and_ignores_flags(self):
        self.regex_language_setup({0: "ass", 1: "srt", 2: "ass"}, ["ass", "srt"])
        self.assertEqual(2, self.player.evalRegexSubPrefs())       # flagged ASS beats unflagged SRT

    def test_regex_language_keeps_other_language_out(self):
        self.regex_language_setup({0: "ass", 1: "srt", 2: "srt"}, ["ass", "srt"])
        self.assertEqual(1, self.player.evalRegexSubPrefs())       # jpn ASS is the wrong language

    def test_regex_without_language_match_acts_as_before(self):
        self.regex_language_setup({0: "ass", 1: "srt", 2: "ass"}, ["ass", "srt"])
        settings.SubtitlePrefs = [(set(), [("French", "fre")])]
        self.assertEqual(0, self.player.evalRegexSubPrefs())

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
        player.playing_file = lambda: filename
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


class StoredPreferenceAfterAudioChangeTests(unittest.TestCase):
    """User switches the audio (en -> fr): the conditional rules then switch the subtitles off (fre:non). The stored
    preference must end up with the subtitles disabled, not the state from before the rules ran."""

    def setUp(self):
        import prefutils
        self.module = prefutils
        self.stored = []
        self.saved = []
        self.old = (prefutils.CustomMediaPreference, prefutils.media_preference_manager,
                    {k: getattr(settings, k, None) for k in ("service_enabled", "at_least_one_pref_on",
                                                             "is_store_user_preference_for_player")})
        state = self.state = {"audio": 0, "sub": 1, "enabled": True}
        stored = self.stored

        class Pref:
            @staticmethod
            def from_player(player):
                return (player.getSelectedAudioIndex(), player.getSelectedSubtitleIndex(), player.selected_sub_enabled)

        prefutils.CustomMediaPreference = Pref
        prefutils.media_preference_manager = types.SimpleNamespace(
            add_preference=stored.append, save_preferences=lambda: self.saved.append(1))
        settings.service_enabled = True
        settings.at_least_one_pref_on = True
        settings.is_store_user_preference_for_player = staticmethod(lambda _p: True)

        player = object.__new__(LangPrefMan_Player)
        player.LPM_initial_run_done = True
        player.isPlayingVideo = lambda: True
        player.audio_changed = False
        player.lpm_expected_audio_index = None
        player.lpm_audio_target = None
        player.selected_audio_stream = {"index": 0, "language": "eng", "name": "English"}
        player.selected_sub = {"index": 1, "language": "fre", "name": "French"}
        player.selected_sub_enabled = True
        player.is_ignore_audio_change_index = lambda _i: False
        player.sub_convert_quiet_until = 0
        player.getSelectedSubtitleLanguage = lambda: "fre"
        player.getSelectedAudioLanguage = lambda: "fre" if state["audio"] else "eng"
        player.getSelectedAudioIndex = lambda: player.selected_audio_stream["index"]
        player.getSelectedSubtitleIndex = lambda: state["sub"]

        def get_details():
            player.selected_audio_stream = {"index": state["audio"], "language": "eng", "name": "x"}
            player.selected_sub_enabled = state["enabled"]
            return True

        player.getDetails = get_details
        player.refresh_subtitle_baseline = lambda: get_details()   # the real one re-reads the state
        player.start_sub_converter = lambda **_kw: None

        def eval_prefs():
            state["enabled"] = False          # fre:non - the rules switch the subtitles off

        player.evalPrefs = eval_prefs
        self.player = player

    def tearDown(self):
        self.module.CustomMediaPreference, self.module.media_preference_manager = self.old[0], self.old[1]

    def test_rules_switching_subs_off_after_a_user_audio_change_are_stored(self):
        self.state["audio"] = 1               # the user picked the French audio in the GUI
        self.player.onAVChange()
        self.assertEqual((1, 1, True), self.stored[0])      # first store: the user's audio choice
        self.assertEqual((1, 1, False), self.stored[-1])    # last store: subtitles disabled by the rules
        self.assertEqual(2, len(self.stored))

    def test_no_second_store_when_the_rules_leave_the_subtitles_alone(self):
        self.state["audio"] = 1
        self.player.evalPrefs = lambda: None
        self.player.onAVChange()
        self.assertEqual(1, len(self.stored))


class ParisianTitleTests(unittest.TestCase):
    def test_parisian_titles_read_as_french_from_france(self):
        import langutils
        for name in ("French (Parisian)", "Français (Parisien)", "Française (Parisienne)", "Parisian French"):
            stream = {"language": "fre", "name": name}
            self.assertEqual(("fre", "FR"), langutils.stream_tag(stream), name)
            self.assertEqual(2, langutils.match_score("fr-FR", stream, "Subtitle"), name)
            self.assertEqual(0, langutils.match_score("fr-CA", stream, "Subtitle"), name)
            self.assertEqual(1, langutils.match_score("fre", stream, "Subtitle"), name)

    def test_a_parisian_title_without_a_language_tag_is_french_from_france(self):
        import langutils
        self.assertEqual(("fre", "FR"), langutils.stream_tag({"language": "und", "name": "French (Parisian)"}))


class CondRecheckAfterOwnAudioSwitchTests(unittest.TestCase):
    """refresh_subtitle_baseline() asks for a second conditional-subtitle run after LPM's own audio switch only when
    the first run did not already evaluate the rules against the switched track."""

    def player(self, evaluated_target):
        player = object.__new__(LangPrefMan_Player)
        player.lpm_audio_target = 1
        player.lpm_expected_audio_index = 1
        player.LPM_initial_run_done = False
        player.cond_recheck_pending = False
        player.cond_eval_target = evaluated_target
        player.selected_audio_stream = {"index": 1, "language": "eng", "name": "English"}
        player.getDetails = lambda: True
        player.getSelectedAudioIndex = lambda: 1
        player.remove_ignore_audio_change_index = lambda _i: None
        return player

    def test_no_second_run_when_the_rules_already_used_the_switched_track(self):
        player = self.player(evaluated_target=1)
        player.refresh_subtitle_baseline()
        self.assertFalse(player.cond_recheck_pending)
        self.assertIsNone(player.cond_eval_target)

    def test_second_run_when_the_rules_did_not_see_the_switched_track(self):
        player = self.player(evaluated_target=None)
        player.refresh_subtitle_baseline()
        self.assertTrue(player.cond_recheck_pending)

    def test_cond_audio_stream_remembers_the_track_it_returned(self):
        player = self.player(evaluated_target=None)
        player.audiostreams = [{"index": 0, "language": "fre"}, {"index": 1, "language": "eng"}]
        self.assertEqual(1, player.cond_audio_stream()["index"])
        self.assertEqual(1, player.cond_eval_target)

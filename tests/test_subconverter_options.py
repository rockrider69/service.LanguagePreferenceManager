import os
import sys
import threading
import time
import types
import unittest
import xml.etree.ElementTree as ET

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
LIB = os.path.join(ROOT, "resources", "lib")
for path in (ROOT, LIB):
    if path not in sys.path:
        sys.path.insert(0, path)

for name in ("xbmc", "xbmcvfs", "xbmcaddon", "xbmcgui"):
    sys.modules.setdefault(name, types.ModuleType(name))
sys.modules["xbmc"].getLocalizedString = getattr(sys.modules["xbmc"], "getLocalizedString", lambda _i: "")
sys.modules["xbmc"].sleep = getattr(sys.modules["xbmc"], "sleep", lambda _ms: None)
for attr in ("Player", "Monitor"):
    if not hasattr(sys.modules["xbmc"], attr):
        setattr(sys.modules["xbmc"], attr, type(attr, (), {}))
if not getattr(sys.modules["xbmcaddon"], "Addon", None):
    sys.modules["xbmcaddon"].Addon = lambda: types.SimpleNamespace(getSetting=lambda _key: "")
sys.modules["xbmcvfs"].translatePath = getattr(sys.modules["xbmcvfs"], "translatePath", lambda p: p)

import colorpick
import langutils
import subconvert

SETTINGS = ET.parse(os.path.join(ROOT, "resources", "settings.xml")).getroot()


def setting(setting_id):
    return [s for s in SETTINGS.iter("setting") if s.get("id") == setting_id][0]


class ColorTests(unittest.TestCase):
    def test_colors_are_read_as_rrggbb_rgb_with_or_without_hash(self):
        for text, expected in (("#ff8800", "#FF8800"), ("FF8800", "#FF8800"), ("f80", "#FF8800"), ("#F80", "#FF8800"),
                               (" #00ffff ", "#00FFFF")):
            self.assertEqual(expected, subconvert.normalize_color(text), text)

    def test_anything_else_is_not_a_color(self):
        for text in ("", None, "yellow", "#12", "#12345", "#1234567", "GG0000", "#FF 88 00"):
            self.assertIsNone(subconvert.normalize_color(text), repr(text))

    def test_the_presets_are_valid_and_start_with_the_old_yellow(self):
        self.assertEqual("#FFFF00", subconvert.COLOR_PRESETS[0])
        self.assertEqual(subconvert.DEFAULT_COLOR, subconvert.COLOR_PRESETS[0])
        for color in subconvert.COLOR_PRESETS:
            self.assertEqual(color, subconvert.normalize_color(color))
        self.assertEqual(len(subconvert.COLOR_PRESETS), len(set(subconvert.COLOR_PRESETS)))

    def events(self):
        return [(1000, 2000, "0,0,Default,,0,0,0,,Hello"), (3000, 4000, "1,0,Default,,0,0,0,,World")]

    def test_srt_is_yellow_by_default_and_in_the_chosen_color(self):
        srt, count = subconvert.events_to_srt(self.events(), "", None, "S_TEXT/ASS")
        self.assertEqual(2, count)
        self.assertIn('<font color="#FFFF00">Hello</font>', srt)
        srt, _ = subconvert.events_to_srt(self.events(), "", None, "S_TEXT/ASS", "#ff8800")
        self.assertIn('<font color="#FF8800">Hello</font>', srt)
        self.assertNotIn("#FFFF00", srt)

    def test_an_invalid_color_falls_back_to_yellow(self):
        srt, _ = subconvert.events_to_srt(self.events(), "", None, "S_TEXT/ASS", "nonsense")
        self.assertIn('<font color="#FFFF00">', srt)

    def test_another_color_is_another_copy_but_the_default_keeps_its_name(self):
        args = ("/data", "/videos/Movie.mkv", 1, "jpn", None, "srt")
        default = subconvert.target_path(*args)
        self.assertEqual(default, subconvert.target_path(*args, color="#FFFF00"))
        self.assertEqual(default, subconvert.target_path(*args, color=None))
        self.assertNotEqual(default, subconvert.target_path(*args, color="#FF8800"))
        self.assertNotEqual(subconvert.target_path(*args, color="#FF8800"), subconvert.target_path(*args, color="#00FFFF"))

    def test_an_ass_copy_keeps_its_own_name_whatever_the_color(self):
        args = ("/data", "/videos/Movie.mkv", 1, "jpn", None, "ass")
        self.assertEqual(subconvert.target_path(*args), subconvert.target_path(*args, color="#FF8800"))


class SettingsFileTests(unittest.TestCase):
    def test_ten_audio_language_spinners_default_to_japanese_korean_chinese_then_none(self):
        defaults = []
        for n in range(1, 11):
            spinner = setting("SubConvLang%02d" % n)
            self.assertEqual("spinner", spinner.find("control").get("type"))
            defaults.append(spinner.find("default").text)
        self.assertEqual(["24", "25", "6"] + ["45"] * 7, defaults)

    def test_the_language_spinners_hide_when_the_converter_is_off_or_all_languages_is_on(self):
        for n in (1, 10):
            conditions = {c.get("setting"): (c.get("operator"), c.text)
                          for c in setting("SubConvLang%02d" % n).iter("condition")}
            self.assertEqual({"subConverter": ("is", "true"), "subConverterAll": ("is", "false")}, conditions)

    def test_color_spinner_has_eight_presets_and_a_custom_entry(self):
        options = setting("subConverterColor").findall("./constraints/options/option")
        self.assertEqual([str(i) for i in range(len(subconvert.COLOR_PRESETS) + 1)], [o.text for o in options])
        self.assertEqual("0", setting("subConverterColor").find("default").text)

    def test_the_hex_field_shows_only_for_the_custom_entry(self):
        conditions = {c.get("setting"): c.text for c in setting("subConverterColorHex").iter("condition")}
        self.assertEqual({"subConverter": "true", "subConverterColor": str(len(subconvert.COLOR_PRESETS))}, conditions)

    def test_the_converter_toggle_no_longer_needs_the_regex_filter_or_the_conditional_rules(self):
        toggle = setting("subConverter")
        self.assertIsNone(toggle.find("dependencies"))
        self.assertEqual("false", toggle.find("default").text)
        self.assertEqual("false", setting("subConverterAll").find("default").text)


class ResolveColorTests(unittest.TestCase):
    def test_presets_and_the_typed_color(self):
        self.assertEqual(("#FFFF00", True), subconvert.resolve_color(0))
        self.assertEqual(("#87CEFA", True), subconvert.resolve_color("7", "ignored"))
        self.assertEqual(("#FF8800", True), subconvert.resolve_color(8, "ff8800"))

    def test_a_bad_typed_color_or_choice_is_yellow(self):
        self.assertEqual(("#FFFF00", False), subconvert.resolve_color(8, "red"))
        self.assertEqual(("#FFFF00", False), subconvert.resolve_color(8))
        self.assertEqual(("#FFFF00", True), subconvert.resolve_color(""))
        self.assertEqual(("#FFFF00", True), subconvert.resolve_color("x"))


class FakeDialog:
    def __init__(self, picker=None, selected=-1):
        self.asked = []
        self.selected = selected
        if picker is not None:
            self.colorpicker = picker

    def select(self, heading, labels):
        self.asked.append(("select", heading, list(labels)))
        return self.selected


class FakeSettingsStore:
    def __init__(self):
        self.values = {}

    def setSetting(self, key, value):
        self.values[key] = value


class ColorPickTests(unittest.TestCase):
    LABELS = ["Yellow", "White", "Cyan", "Green", "Orange", "Pink", "Red", "Light blue"]

    def test_the_dialog_answer_is_read_with_or_without_alpha(self):
        self.assertEqual("#FF8800", colorpick.from_dialog("FFFF8800"))
        self.assertEqual("#FF8800", colorpick.from_dialog("80ff8800"))
        self.assertEqual("#FF8800", colorpick.from_dialog("FF8800"))
        self.assertEqual("#FF8800", colorpick.from_dialog("#ff8800"))
        for nothing in ("", None, "zz", "FF88"):
            self.assertIsNone(colorpick.from_dialog(nothing), repr(nothing))

    def test_the_chart_starts_on_the_current_color_and_returns_the_pick(self):
        seen = []
        dialog = FakeDialog(picker=lambda heading, selected: seen.append((heading, selected)) or "FF123456")
        self.assertEqual("#123456", colorpick.choose(dialog, "Color", "#FF8800", self.LABELS))
        self.assertEqual([("Color", "FFFF8800")], seen)
        self.assertEqual([], dialog.asked)

    def test_cancelling_the_chart_picks_nothing_and_does_not_open_the_list(self):
        dialog = FakeDialog(picker=lambda *_a: "")
        self.assertIsNone(colorpick.choose(dialog, "Color", "#FFFF00", self.LABELS))
        self.assertEqual([], dialog.asked)

    def test_kodi_without_the_chart_gets_the_list_of_presets(self):
        dialog = FakeDialog(selected=6)
        self.assertEqual("#FF4040", colorpick.choose(dialog, "Color", "#FFFF00", self.LABELS))
        self.assertEqual([("select", "Color", self.LABELS)], dialog.asked)
        self.assertIsNone(colorpick.choose(FakeDialog(selected=-1), "Color", "#FFFF00", self.LABELS))

    def test_a_chart_that_raises_falls_back_to_the_list(self):
        def broken(*_a):
            raise RuntimeError("no color dialog")
        dialog = FakeDialog(picker=broken, selected=1)
        self.assertEqual("#FFFFFF", colorpick.choose(dialog, "Color", "#FFFF00", self.LABELS))

    def test_a_chosen_preset_is_stored_as_that_preset(self):
        addon = FakeSettingsStore()
        colorpick.store(addon, "#00FFFF")
        self.assertEqual({"subConverterColor": "2"}, addon.values)

    def test_any_other_color_is_stored_as_custom(self):
        addon = FakeSettingsStore()
        colorpick.store(addon, "#123456")
        self.assertEqual({"subConverterColorHex": "123456", "subConverterColor": "8"}, addon.values)
        self.assertEqual(("#123456", True), subconvert.resolve_color(
            addon.values["subConverterColor"], addon.values["subConverterColorHex"]))

    def test_the_settings_have_a_pick_button_that_runs_the_script(self):
        button = setting("subConverterColorPick")
        self.assertEqual("button", button.find("control").get("type"))
        self.assertEqual("RunScript(service.languagepreferencemanager,pick_color)", button.find("./control/data").text)


class FakeAddon:
    def __init__(self, **values):
        self.values = {"SubConvLang%02d" % n: str(v) for n, v in enumerate((24, 25, 6, 45, 45, 45, 45, 45, 45, 45), 1)}
        self.values.update({k: str(v) for k, v in values.items()})

    def getSetting(self, key):
        return self.values.get(key, "")


class ReadSettingsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # the real module, whatever other test files put into sys.modules under the same name
        import importlib.util
        spec = importlib.util.spec_from_file_location("lpm_real_prefsettings", os.path.join(LIB, "prefsettings.py"))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        cls.holder = module.settings

    def read(self, **values):
        holder = self.holder.__new__(self.holder)
        holder.sub_converter_on = True
        holder.read_sub_converter(FakeAddon(**values))
        return holder

    def test_defaults_are_japanese_korean_chinese_and_yellow(self):
        s = self.read()
        self.assertEqual(["jpn", "kor", "chi"], s.sub_converter_langs)
        self.assertFalse(s.sub_converter_all)
        self.assertEqual("#FFFF00", s.sub_converter_color)

    def test_up_to_ten_languages_none_and_duplicates_are_dropped(self):
        values = {"SubConvLang%02d" % n: v for n, v in enumerate((11, 15, 8, 11, 24, 25, 6, 45, 46, 17), 1)}
        s = self.read(**values)
        self.assertLessEqual(len(s.sub_converter_langs), 10)
        self.assertNotIn(langutils.NON, s.sub_converter_langs)
        self.assertEqual(len(s.sub_converter_langs), len(set(s.sub_converter_langs)))
        self.assertIn("any", s.sub_converter_langs)

    def test_the_all_languages_button(self):
        self.assertTrue(self.read(subConverterAll="true").sub_converter_all)

    def test_preset_colors_and_a_typed_one(self):
        self.assertEqual("#FFFFFF", self.read(subConverterColor=1).sub_converter_color)
        self.assertEqual("#87CEFA", self.read(subConverterColor=7).sub_converter_color)
        self.assertEqual("#FF8800", self.read(subConverterColor=8, subConverterColorHex="ff8800").sub_converter_color)
        self.assertEqual("#FF8800", self.read(subConverterColor=8, subConverterColorHex="#f80").sub_converter_color)

    def test_a_bad_typed_color_or_choice_gives_yellow(self):
        self.assertEqual("#FFFF00", self.read(subConverterColor=8, subConverterColorHex="red").sub_converter_color)
        self.assertEqual("#FFFF00", self.read(subConverterColor=8).sub_converter_color)
        self.assertEqual("#FFFF00", self.read(subConverterColor="").sub_converter_color)
        self.assertEqual("#FFFF00", self.read(subConverterColor="x").sub_converter_color)


class ConverterGateTests(unittest.TestCase):
    """The converter works with any setting, not only with the regex filter or the conditional rules."""

    @classmethod
    def setUpClass(cls):
        logger = types.ModuleType("logger")
        logger.LOG_NONE, logger.LOG_INFO, logger.LOG_DEBUG, logger.LOG_ERROR = range(4)
        logger.log = lambda *_a: None
        sys.modules.setdefault("logger", logger)
        sys.modules.setdefault("custom_media_preference", types.SimpleNamespace(
            media_preference_manager=types.SimpleNamespace(), CustomMediaPreference=type("C", (), {})))
        import prefutils
        cls.prefutils = prefutils

    def setUp(self):
        s = self.prefutils.settings
        self.saved = {k: getattr(s, k, None) for k in ("sub_converter_on", "sub_converter_all", "sub_converter_langs",
                                                       "regex_sub_filter_enabled", "condsub_prefs_on")}
        s.sub_converter_on, s.sub_converter_all, s.sub_converter_langs = True, False, ["jpn", "kor", "chi"]
        s.regex_sub_filter_enabled = s.condsub_prefs_on = False

    def tearDown(self):
        for k, v in self.saved.items():
            setattr(self.prefutils.settings, k, v)

    def player(self):
        player = object.__new__(self.prefutils.LangPrefMan_Player)
        player.sub_converting = False
        player.sub_convert_pending = False
        player.runs = threading.Event()
        player._sub_converter_run = player.runs.set
        return player

    def test_it_starts_with_neither_the_regex_filter_nor_the_conditional_rules(self):
        player = self.player()
        player.start_sub_converter()
        self.assertTrue(player.runs.wait(2))

    def test_it_stays_off_when_its_toggle_is_off(self):
        self.prefutils.settings.sub_converter_on = False
        player = self.player()
        player.start_sub_converter()
        self.assertFalse(player.runs.wait(0.2))

    def audio(self, language, name=""):
        return {"index": 0, "language": language, "name": name}

    def test_default_languages(self):
        wanted = self.prefutils.LangPrefMan_Player.sub_converter_audio_wanted
        for language in ("jpn", "ja", "kor", "chi", "zh"):
            self.assertTrue(wanted(self.audio(language)), language)
        for language in ("eng", "fre", "ger", ""):
            self.assertFalse(wanted(self.audio(language)), language)

    def test_chosen_languages_and_all(self):
        wanted = self.prefutils.LangPrefMan_Player.sub_converter_audio_wanted
        settings = self.prefutils.settings
        settings.sub_converter_langs = ["fre", "ger", "eng"]
        self.assertTrue(wanted(self.audio("fre")))
        self.assertTrue(wanted(self.audio("deu")))
        self.assertFalse(wanted(self.audio("jpn")))
        settings.sub_converter_langs = []
        self.assertFalse(wanted(self.audio("eng")))
        settings.sub_converter_all = True
        self.assertTrue(wanted(self.audio("eng")))
        self.assertTrue(wanted(self.audio("")))


class WatcherTests(unittest.TestCase):
    """The 10 second subtitle watcher also serves the sub converter (a subtitle switched on or off during playback)."""

    @classmethod
    def setUpClass(cls):
        ConverterGateTests.setUpClass()
        cls.prefutils = ConverterGateTests.prefutils

    def run_one_round(self, **flags):
        prefutils = self.prefutils
        settings = prefutils.settings
        saved = {k: getattr(settings, k, None) for k in ("storeCustomMediaPreferences", "sub_converter_on")}
        settings.storeCustomMediaPreferences = flags.get("store", False)
        settings.sub_converter_on = flags.get("converter", False)
        calls = []

        class Monitor:
            def abortRequested(self):
                return False

            def waitForAbort(self, _seconds):
                return True                       # stop after the first round

        player = types.SimpleNamespace(isPlayingVideo=lambda: flags.get("playing", True),
                                       detect_subtitle_change=lambda: calls.append(1))
        old_monitor = prefutils.xbmc.Monitor
        prefutils.xbmc.Monitor = Monitor
        try:
            prefutils.LangPrefWatcher(player, check_interval=10).run()
        finally:
            prefutils.xbmc.Monitor = old_monitor
            for k, v in saved.items():
                setattr(settings, k, v)
        return len(calls)

    def test_it_looks_for_the_sub_converter_without_stored_preferences(self):
        self.assertEqual(1, self.run_one_round(converter=True))

    def test_it_still_looks_for_stored_preferences(self):
        self.assertEqual(1, self.run_one_round(store=True))

    def test_it_does_nothing_when_neither_is_on_or_nothing_plays(self):
        self.assertEqual(0, self.run_one_round())
        self.assertEqual(0, self.run_one_round(converter=True, playing=False))


class SubtitleEventTests(unittest.TestCase):
    """Kodi announces subtitle changes (Player.OnPropertyChanged): no waiting for the watcher."""

    @classmethod
    def setUpClass(cls):
        ConverterGateTests.setUpClass()
        cls.prefutils = ConverterGateTests.prefutils

    def setUp(self):
        s = self.prefutils.settings
        self.saved = {k: getattr(s, k, None) for k in ("storeCustomMediaPreferences", "sub_converter_on")}
        s.storeCustomMediaPreferences, s.sub_converter_on = False, True
        self.old_delay = self.prefutils.LangPrefMan_Player.SUB_EVENT_DELAY
        self.prefutils.LangPrefMan_Player.SUB_EVENT_DELAY = 0.02

    def tearDown(self):
        for k, v in self.saved.items():
            setattr(self.prefutils.settings, k, v)
        self.prefutils.LangPrefMan_Player.SUB_EVENT_DELAY = self.old_delay

    def player(self):
        player = object.__new__(self.prefutils.LangPrefMan_Player)
        player.detected = threading.Semaphore(0)
        player.calls = 0

        def detect():
            player.calls += 1
            player.detected.release()

        player.detect_subtitle_change = detect
        player.isPlayingVideo = lambda: True
        return player

    def monitor(self, player):
        monitor = object.__new__(self.prefutils.LangPref_Monitor)
        monitor.player = player
        return monitor

    def test_a_subtitle_property_notification_makes_the_player_look(self):
        player = self.player()
        monitor = self.monitor(player)
        monitor.onNotification("xbmc", "Player.OnPropertyChanged", '{"player":{"playerid":-1},"property":{"subtitleenabled":true}}')
        self.assertTrue(player.detected.acquire(timeout=2))
        self.assertTrue(player.subtitle_events_seen)

    def test_a_track_change_notification_too(self):
        player = self.player()
        self.monitor(player).onNotification("xbmc", "Player.OnPropertyChanged", '{"property":{"currentsubtitle":{"index":1}}}')
        self.assertTrue(player.detected.acquire(timeout=2))

    def test_other_notifications_and_properties_are_ignored(self):
        player = self.player()
        monitor = self.monitor(player)
        monitor.onNotification("xbmc", "Player.OnAVChange", '{"property":{"subtitleenabled":true}}')
        monitor.onNotification("xbmc", "Player.OnPropertyChanged", '{"property":{"repeat":"all"}}')
        monitor.onNotification("xbmc", "Player.OnPropertyChanged", "not json")
        monitor.onNotification("xbmc", "Player.OnPropertyChanged", "null")
        self.assertFalse(player.detected.acquire(timeout=0.3))
        self.assertFalse(getattr(player, "subtitle_events_seen", False))

    def test_a_monitor_without_a_player_does_nothing(self):
        monitor = self.monitor(None)
        monitor.onNotification("xbmc", "Player.OnPropertyChanged", '{"property":{"subtitleenabled":true}}')

    def test_the_events_of_one_change_are_merged(self):
        player = self.player()
        for _ in range(4):
            player.on_subtitle_event()
        self.assertTrue(player.detected.acquire(timeout=2))
        self.assertFalse(player.detected.acquire(timeout=0.3))
        self.assertEqual(1, player.calls)

    def test_a_change_LPM_made_itself_is_not_looked_at_as_the_users(self):
        player = self.player()
        player.sub_event_quiet_until = time.time() + 5
        player.on_subtitle_event()
        self.assertFalse(player.detected.acquire(timeout=0.3))
        player.sub_event_quiet_until = 0
        player.on_subtitle_event()
        self.assertTrue(player.detected.acquire(timeout=2))

    def test_nothing_is_looked_at_when_neither_the_converter_nor_stored_preferences_are_on(self):
        self.prefutils.settings.sub_converter_on = False
        player = self.player()
        player.on_subtitle_event()
        self.assertFalse(player.detected.acquire(timeout=0.3))

    def test_lpm_switching_the_subtitle_starts_the_quiet_time(self):
        xbmc = self.prefutils.xbmc
        seen = []
        xbmc.Player.setSubtitleStream = lambda _self, index: seen.append(("stream", index))
        xbmc.Player.showSubtitles = lambda _self, visible: seen.append(("show", visible))
        try:
            player = self.player()
            player.setSubtitleStream(2)
            self.assertGreater(player.sub_event_quiet_until, time.time())
            player.sub_event_quiet_until = 0
            player.showSubtitles(True)
            self.assertGreater(player.sub_event_quiet_until, time.time())
            self.assertEqual([("stream", 2), ("show", True)], seen)
        finally:
            del xbmc.Player.setSubtitleStream, xbmc.Player.showSubtitles

    def test_the_watcher_relaxes_once_kodi_announces_the_changes(self):
        waits = []

        class Monitor:
            def abortRequested(self):
                return len(waits) > 130

            def waitForAbort(self, seconds):
                waits.append(seconds)
                return len(waits) > 130              # leave after a while

        prefutils = self.prefutils
        old = prefutils.xbmc.Monitor
        prefutils.xbmc.Monitor = Monitor
        try:
            player = types.SimpleNamespace(isPlayingVideo=lambda: False, subtitle_events_seen=False)
            watcher = prefutils.LangPrefWatcher(player, check_interval=10)
            watcher.run()
            rounds_without = len(waits)
            waits.clear()
            player.subtitle_events_seen = True
            prefutils.LangPrefWatcher(player, check_interval=10).run()
        finally:
            prefutils.xbmc.Monitor = old
        self.assertGreater(rounds_without, 0)
        self.assertEqual(131, len(waits))
        self.assertEqual(60, prefutils.LangPrefWatcher.SAFETY_INTERVAL)


if __name__ == "__main__":
    unittest.main()

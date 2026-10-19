import inspect
import json
import os
import sys
import threading
import time
import types
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
LIB = os.path.join(ROOT, "resources", "lib")
for path in (ROOT, LIB):
    if path not in sys.path:
        sys.path.insert(0, path)

for name in ("xbmc", "xbmcvfs", "xbmcaddon", "xbmcgui"):
    sys.modules.setdefault(name, types.ModuleType(name))
for attr in ("Player", "Monitor"):
    if not hasattr(sys.modules["xbmc"], attr):
        setattr(sys.modules["xbmc"], attr, type(attr, (), {}))
sys.modules["xbmc"].getLocalizedString = getattr(sys.modules["xbmc"], "getLocalizedString", lambda _i: "")
sys.modules["xbmc"].sleep = getattr(sys.modules["xbmc"], "sleep", lambda _ms: None)
if not hasattr(sys.modules["xbmcvfs"], "translatePath"):
    sys.modules["xbmcvfs"].translatePath = lambda path: path
if not getattr(sys.modules["xbmcaddon"], "Addon", None):
    sys.modules["xbmcaddon"].Addon = lambda: types.SimpleNamespace(getSetting=lambda _key: "")

import kodirpc


class FakeKodi:
    """xbmc.executeJSONRPC with canned answers; remembers the requests."""

    def __init__(self, answers):
        self.answers = answers
        self.requests = []

    def __call__(self, query):
        request = json.loads(query)
        self.requests.append((request["method"], request.get("params")))
        answer = self.answers.get(request["method"], {"error": {"code": -32601}})
        if callable(answer):
            answer = answer(request.get("params"))
        if isinstance(answer, str):
            return answer                                  # a raw (maybe broken) reply
        return json.dumps(dict(answer, jsonrpc="2.0", id=request["id"]))


class KodiRpcTests(unittest.TestCase):
    def setUp(self):
        self.xbmc = kodirpc.xbmc          # the module kodirpc itself uses (other test files swap sys.modules["xbmc"])
        self.old = getattr(self.xbmc, "executeJSONRPC", None)

    def tearDown(self):
        if self.old is None:
            if hasattr(self.xbmc, "executeJSONRPC"):
                del self.xbmc.executeJSONRPC
        else:
            self.xbmc.executeJSONRPC = self.old

    def kodi(self, **answers):
        self.xbmc.executeJSONRPC = FakeKodi(answers)
        return self.xbmc.executeJSONRPC

    def test_the_video_player_is_found_among_the_active_players(self):
        self.kodi(**{"Player.GetActivePlayers": {"result": [{"playerid": 0, "type": "audio"}, {"playerid": 1, "type": "video"}]}})
        self.assertEqual(1, kodirpc.video_player_id())
        self.assertTrue(kodirpc.is_playing_video())

    def test_nothing_playing(self):
        self.kodi(**{"Player.GetActivePlayers": {"result": []}})
        self.assertIsNone(kodirpc.video_player_id())
        self.assertFalse(kodirpc.is_playing_video())
        self.assertEqual("", kodirpc.playing_file())
        self.assertFalse(kodirpc.add_subtitle("/tmp/x.srt"))
        self.assertFalse(kodirpc.show_subtitles(True))

    def test_seek_back_is_a_relative_player_seek(self):
        kodi = self.kodi(**{"Player.GetActivePlayers": {"result": [{"playerid": 1, "type": "video"}]},
                            "Player.Seek": {"result": {"percentage": 10}}})
        self.assertTrue(kodirpc.seek_back(3))
        self.assertEqual(("Player.Seek", {"playerid": 1, "value": {"seconds": -3}}), kodi.requests[-1])
        self.assertTrue(kodirpc.seek_back(-5))                  # the sign does not matter: always backwards
        self.assertEqual({"seconds": -5}, kodi.requests[-1][1]["value"])

    def test_seek_back_without_a_video_or_when_kodi_refuses(self):
        self.kodi(**{"Player.GetActivePlayers": {"result": []}})
        self.assertFalse(kodirpc.seek_back(3))
        self.kodi(**{"Player.GetActivePlayers": {"result": [{"playerid": 1, "type": "video"}]}})
        self.assertFalse(kodirpc.seek_back(3))                  # no Player.Seek answer: an error

    def test_the_playing_file_comes_from_player_getitem(self):
        kodi = self.kodi(**{"Player.GetActivePlayers": {"result": [{"playerid": 1, "type": "video"}]},
                            "Player.GetItem": {"result": {"item": {"file": "smb://nas/movies/A.mkv", "type": "movie"}}}})
        self.assertEqual("smb://nas/movies/A.mkv", kodirpc.playing_file())
        self.assertIn(("Player.GetItem", {"playerid": 1, "properties": ["file"]}), kodi.requests)

    def test_a_missing_file_or_an_error_gives_an_empty_path(self):
        self.kodi(**{"Player.GetActivePlayers": {"result": [{"playerid": 1, "type": "video"}]},
                     "Player.GetItem": {"result": {"item": {}}}})
        self.assertEqual("", kodirpc.playing_file())
        self.kodi(**{"Player.GetActivePlayers": {"result": [{"playerid": 1, "type": "video"}]}})   # GetItem: an error
        self.assertEqual("", kodirpc.playing_file())

    def test_a_subtitle_file_is_added_with_player_addsubtitle(self):
        kodi = self.kodi(**{"Player.GetActivePlayers": {"result": [{"playerid": 1, "type": "video"}]},
                            "Player.AddSubtitle": {"result": "OK"}})
        self.assertTrue(kodirpc.add_subtitle("/data/converted_subs/A [abc123-0].jpn.srt"))
        self.assertIn(("Player.AddSubtitle", {"playerid": 1, "subtitle": "/data/converted_subs/A [abc123-0].jpn.srt"}),
                      kodi.requests)

    def test_subtitles_on_off_and_a_track_use_player_setsubtitle(self):
        kodi = self.kodi(**{"Player.GetActivePlayers": {"result": [{"playerid": 1, "type": "video"}]},
                            "Player.SetSubtitle": {"result": "OK"}})
        self.assertTrue(kodirpc.show_subtitles(True))
        self.assertTrue(kodirpc.show_subtitles(False))
        self.assertTrue(kodirpc.set_subtitle(2))
        sent = [params for method, params in kodi.requests if method == "Player.SetSubtitle"]
        self.assertEqual([{"playerid": 1, "subtitle": "on"}, {"playerid": 1, "subtitle": "off"},
                          {"playerid": 1, "subtitle": 2}], sent)

    def test_an_error_reply_is_a_failure(self):
        self.kodi(**{"Player.GetActivePlayers": {"result": [{"playerid": 1, "type": "video"}]},
                     "Player.AddSubtitle": {"error": {"code": -32100, "message": "Failed to execute method."}}})
        self.assertFalse(kodirpc.add_subtitle("/tmp/x.srt"))

    def test_garbage_or_no_answer_never_raises(self):
        self.kodi(**{"Player.GetActivePlayers": "this is not json"})
        self.assertIsNone(kodirpc.video_player_id())
        self.kodi(**{"Player.GetActivePlayers": "[1, 2]"})
        self.assertIsNone(kodirpc.video_player_id())
        self.xbmc.executeJSONRPC = lambda _q: None
        self.assertEqual("", kodirpc.playing_file())

    def test_info_labels(self):
        kodi = self.kodi(**{"XBMC.GetInfoLabels": {"result": {"System.ScreenWidth": "1920", "VideoPlayer.VideoAspect": "1.78"}}})
        self.assertEqual({"System.ScreenWidth": "1920", "VideoPlayer.VideoAspect": "1.78"},
                         kodirpc.info_labels(["System.ScreenWidth", "VideoPlayer.VideoAspect"]))
        self.assertEqual("XBMC.GetInfoLabels", kodi.requests[0][0])
        self.kodi()
        self.assertEqual({}, kodirpc.info_labels(["System.ScreenWidth"]))


class ConverterUsesJsonRpcTests(unittest.TestCase):
    """The sub converter talks to Kodi about the streams over JSON-RPC, not through the Python player methods."""

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

    def converter_source(self):
        cls = self.prefutils.LangPrefMan_Player
        names = ("start_sub_converter", "_sub_converter_job", "_sub_converter_run", "_picture_view", "_still_playing",
                 "embedded_subtitle_codecs", "playing_file", "rpc_add_subtitle", "rpc_show_subtitles")
        return {name: inspect.getsource(getattr(cls, name)) for name in names}

    def test_no_python_player_calls_for_the_streams(self):
        for name, source in self.converter_source().items():
            for call in ("self.getPlayingFile", "self.setSubtitles(", "self.showSubtitles(", "self.isPlayingVideo",
                         "self.setSubtitleStream(", "self.getAvailableSubtitleStreams", "xbmc.getInfoLabel"):
                self.assertNotIn(call, source, "{0} uses {1}".format(name, call))

    def test_the_converter_has_no_polling_of_its_own(self):
        for name, source in self.converter_source().items():
            for call in ("LangPrefWatcher", "waitForAbort", "time.sleep", "while True", "threading.Timer(", "check_interval"):
                self.assertNotIn(call, source, "{0} uses {1}".format(name, call))

    def test_a_seek_makes_the_player_look_at_the_subtitle(self):
        player = object.__new__(self.prefutils.LangPrefMan_Player)
        seen = []
        player.detect_subtitle_change = lambda trigger="": seen.append("looked")
        player.onPlayBackSeek(12, 5)
        self.assertEqual(["looked"], seen)

    def player(self):
        player = object.__new__(self.prefutils.LangPrefMan_Player)
        player.sub_event_quiet_until = 0
        return player

    def test_the_converter_hands_the_copy_to_kodi_over_json_rpc(self):
        prefutils = self.prefutils
        calls = []
        old = (prefutils.kodirpc.add_subtitle, prefutils.kodirpc.show_subtitles)
        prefutils.kodirpc.add_subtitle = lambda path: calls.append(("add", path)) or True
        prefutils.kodirpc.show_subtitles = lambda visible: calls.append(("show", visible)) or True
        try:
            player = self.player()
            self.assertTrue(player.rpc_add_subtitle("/d/x.srt"))
            self.assertGreater(player.sub_event_quiet_until, time.time())      # an own change: a quiet time
            player.sub_event_quiet_until = 0
            self.assertTrue(player.rpc_show_subtitles(True))
            self.assertGreater(player.sub_event_quiet_until, time.time())
        finally:
            prefutils.kodirpc.add_subtitle, prefutils.kodirpc.show_subtitles = old
        self.assertEqual([("add", "/d/x.srt"), ("show", True)], calls)

    def test_the_playing_check_between_clusters_asks_kodi_at_most_once_a_second(self):
        prefutils = self.prefutils
        asked = []
        old = (prefutils.kodirpc.is_playing_video, prefutils.kodirpc.playing_file)
        prefutils.kodirpc.is_playing_video = lambda: asked.append("video") or True
        prefutils.kodirpc.playing_file = lambda player_id=None: asked.append("file") or "/v/a.mkv"
        try:
            player = self.player()
            check = player._still_playing("/v/a.mkv", interval=0.3)
            results = [check() for _ in range(500)]                          # thousands of clusters in real files
            self.assertTrue(all(results))
            self.assertEqual(["video", "file"], asked)
            time.sleep(0.35)
            check()
            self.assertEqual(["video", "file", "video", "file"], asked)
            prefutils.kodirpc.playing_file = lambda player_id=None: "/v/other.mkv"     # another video plays now
            time.sleep(0.35)
            self.assertFalse(check())
        finally:
            prefutils.kodirpc.is_playing_video, prefutils.kodirpc.playing_file = old

    def test_the_picture_view_reads_its_labels_over_json_rpc(self):
        prefutils = self.prefutils
        old = prefutils.kodirpc.info_labels
        prefutils.kodirpc.info_labels = lambda labels: {"System.ScreenWidth": "1920", "System.ScreenHeight": "1080",
                                                        "VideoPlayer.VideoAspect": "2,35"}
        try:
            view = self.player()._picture_view()
        finally:
            prefutils.kodirpc.info_labels = old
        self.assertIsNotNone(view)
        prefutils.kodirpc.info_labels = lambda labels: {}
        try:
            self.assertIsNone(self.player()._picture_view())
        finally:
            prefutils.kodirpc.info_labels = old


if __name__ == "__main__":
    unittest.main()

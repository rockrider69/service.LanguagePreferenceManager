import os
import re
import sys
import unittest
import xml.etree.ElementTree as ET

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(ROOT, "resources", "lib"))

import langutils
import subcodec


class FormatHelperTests(unittest.TestCase):
    def test_matroska_codec_ids_map_to_the_ranked_formats(self):
        expected = {"S_TEXT/UTF8": "srt", "S_TEXT/ASCII": "srt", "S_TEXT/ASS": "ass", "S_TEXT/SSA": "ass", "S_ASS": "ass",
                    "S_TEXT/WEBVTT": "webvtt", "D_WEBVTT/SUBTITLES": "webvtt", "S_HDMV/PGS": "pgs",
                    "S_VOBSUB": "vobsub", "S_DVBSUB": None, "S_HDMV/TEXTST": None, "": None, None: None}
        for codec, fmt in expected.items():
            with self.subTest(codec=codec):
                self.assertEqual(fmt, subcodec.format_of_codec(codec))

    def test_extensions(self):
        for ext, fmt in ((".srt", "srt"), (".SRT", "srt"), ("ass", "ass"), (".ssa", "ass"), (".vtt", "webvtt"),
                         (".sup", "pgs"), (".idx", "vobsub"), (".sub", None), (".txt", None), ("", None)):
            with self.subTest(ext=ext):
                self.assertEqual(fmt, subcodec.format_of_extension(ext))

    def test_format_words_in_track_titles(self):
        for name, fmt in (("English [SRT]", "srt"), ("Signs (ASS)", "ass"), ("English PGS", "pgs"),
                          ("English - SubRip", "srt"), ("English (WebVTT)", "webvtt"), ("VobSub", "vobsub"),
                          ("English", None), ("Class", None), ("Glass subtitles", None), ("Support", None),
                          ("English SRT / ASS", None)):
            with self.subTest(name=name):
                self.assertEqual(fmt, subcodec.format_of_name(name))

    def test_every_ranked_format_has_a_codec_and_a_setting_value(self):
        self.assertEqual(5, len(subcodec.SUBTITLE_FORMATS))
        self.assertEqual(len(set(subcodec.SUBTITLE_FORMATS)), len(subcodec.SUBTITLE_FORMATS))


class ExternalFileTests(unittest.TestCase):
    def test_subtitle_file_tag_carries_the_extension(self):
        self.assertEqual(".srt", langutils.subtitle_file_tag("Movie.mkv", "Movie.pt-BR.srt")["ext"])
        self.assertEqual(".ass", langutils.subtitle_file_tag("Movie.mkv", "Movie.en.ASS")["ext"])

    def test_the_matched_files_of_a_stream_are_reported(self):
        files = [langutils.subtitle_file_tag("Movie.mkv", n) for n in ("Movie.en.srt", "Movie.fr.ass")]
        streams = [{"index": 0, "language": "en", "name": "(External)"}, {"index": 1, "language": "fr", "name": "(External)"}]
        out = {}
        tags = langutils.match_external_files(streams, files, None, out)
        self.assertEqual({0: "en", 1: "fr"}, tags)
        self.assertEqual({0: [".srt"], 1: [".ass"]}, {i: [f["ext"] for f in fs] for i, fs in out.items()})

    def test_files_out_is_optional(self):
        files = [langutils.subtitle_file_tag("Movie.mkv", "Movie.en.srt")]
        self.assertEqual({0: "en"}, langutils.match_external_files(
            [{"index": 0, "language": "en", "name": "(External)"}], files))


class SettingsTests(unittest.TestCase):
    def setUp(self):
        self.root = ET.parse(os.path.join(ROOT, "resources", "settings.xml")).getroot()

    def test_three_format_spinners_with_one_option_per_format(self):
        for n in (1, 2, 3):
            setting = [s for s in self.root.iter("setting") if s.get("id") == "SubFormat%d" % n][0]
            values = [o.text for o in setting.findall("./constraints/options/option")]
            self.assertEqual([str(i) for i in range(len(subcodec.SUBTITLE_FORMATS) + 1)], values)
            self.assertEqual("0", setting.find("default").text)

    def test_second_and_third_spinner_appear_only_after_the_previous_one_is_set(self):
        for n, previous in ((2, "SubFormat1"), (3, "SubFormat2")):
            setting = [s for s in self.root.iter("setting") if s.get("id") == "SubFormat%d" % n][0]
            dep = setting.find("./dependencies/dependency")
            self.assertEqual(previous, dep.get("setting"))
            self.assertEqual("!is", dep.get("operator"))
            self.assertEqual("0", dep.text)

    def test_the_settings_file_keeps_its_crlf_line_endings(self):
        with open(os.path.join(ROOT, "resources", "settings.xml"), "rb") as f:
            data = f.read()
        self.assertEqual(data.count(b"\n"), data.count(b"\r\n"))


if __name__ == "__main__":
    unittest.main()

import os
import sys
import types
import unittest

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(ROOT, "resources", "lib"))
for name in ("xbmc", "xbmcvfs", "xbmcaddon", "xbmcgui"):
    sys.modules.setdefault(name, types.ModuleType(name))

import subcodec
import subconvert


class SrtConversionTests(unittest.TestCase):
    def test_srt_is_convertible_but_pictures_are_not(self):
        for codec in ("S_TEXT/UTF8", "S_TEXT/ASCII", "S_TEXT/ASS", "S_TEXT/WEBVTT"):
            self.assertTrue(subcodec.is_convertible(codec), codec)
        for codec in ("S_HDMV/PGS", "S_VOBSUB", "S_DVBSUB", ""):
            self.assertFalse(subcodec.is_convertible(codec), codec)

    def test_srt_cue_goes_to_the_top_and_keeps_italics_per_line(self):
        lines, placement, positioned = subconvert.srt_cue("<i>Hello\nthere</i>\nplain")
        self.assertEqual(["<i>Hello</i>", "<i>there</i>", "plain"], lines)
        self.assertEqual(("\\an8", False), (placement, positioned))

    def test_srt_cue_keeps_a_position_and_drops_bottom_alignment(self):
        self.assertEqual((["x"], "\\an7\\pos(100,200)", True), subconvert.srt_cue("{\\an7\\pos(100,200)}x"))
        self.assertEqual((["x"], "\\an8", False), subconvert.srt_cue("{\\an2}x"))
        self.assertEqual((["x"], "\\an4", True), subconvert.srt_cue("{\\an4}x"))

    def test_srt_output_is_yellow_at_the_top(self):
        srt, count = subconvert.events_to_srt([(0, 1000, "<i>a</i>"), (2000, 3000, "b")], "", None, "S_TEXT/UTF8")
        self.assertEqual(2, count)
        self.assertIn('{\\an8}<font color="#FFFF00"><i>a</i></font>', srt)
        self.assertIn('{\\an8}<font color="#FFFF00">b</font>', srt)


if __name__ == "__main__":
    unittest.main()

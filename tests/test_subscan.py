import os
import sys
import tempfile
import types
import unittest

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(ROOT, "resources", "lib"))
for name in ("xbmc", "xbmcvfs", "xbmcaddon", "xbmcgui"):
    sys.modules.setdefault(name, types.ModuleType(name))

import subcodec
import subconvert


def element(eid, payload):
    id_bytes = eid.to_bytes((eid.bit_length() + 7) // 8, "big")
    return id_bytes + b"\x01" + len(payload).to_bytes(7, "big") + payload


def uint(value):
    return value.to_bytes(max(1, (value.bit_length() + 7) // 8), "big")


def track(number, kind, codec, private=b""):
    body = element(0xD7, uint(number)) + element(0x83, uint(kind)) + element(0x86, codec.encode())
    if private:
        body += element(0x63A2, private)
    return element(0xAE, body)


def simple_block(number, rel, data):
    return element(0xA3, bytes([0x80 | number]) + rel.to_bytes(2, "big") + b"\x00" + data)


def build_mkv(clusters=3):
    """A small Matroska file: video (1), three subtitle tracks (2 SRT, 3 ASS, 4 picture) and `clusters` clusters."""
    tracks = element(0x1654AE6B,
                     track(1, 1, "V_MPEG4/ISO/AVC") + track(2, 17, "S_TEXT/UTF8") +
                     track(3, 17, "S_TEXT/ASS", b"[Script Info]\nPlayResX: 640\n") + track(4, 17, "S_HDMV/PGS"))
    body = tracks
    for n in range(clusters):
        content = element(0xE7, uint(n * 1000)) + simple_block(1, 0, b"V" * 3000)
        content += simple_block(2, 100, ("srt %d" % n).encode())
        content += simple_block(3, 200, ("0,0,Default,,0,0,0,,ass %d" % n).encode())
        content += simple_block(4, 300, b"picture")
        body += element(0x1F43B675, content)
    return element(0x1A45DFA3, element(0x4282, b"matroska")) + element(0x18538067, body)


class FakeFile:
    opened = 0

    def __init__(self, path):
        FakeFile.opened += 1
        with open(path, "rb") as f:
            self.data = f.read()
        self.pos = 0

    def size(self):
        return len(self.data)

    def seek(self, pos, whence=0):
        self.pos = pos

    def readBytes(self, n):
        out = self.data[self.pos:self.pos + n]
        self.pos += len(out)
        return out

    def close(self):
        pass


class ScanTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.video = os.path.join(self.dir, "video.mkv")
        with open(self.video, "wb") as f:
            f.write(build_mkv())
        self.old_file = getattr(sys.modules["xbmcvfs"], "File", None)
        sys.modules["xbmcvfs"].File = FakeFile
        FakeFile.opened = 0

    def tearDown(self):
        if self.old_file is None:
            del sys.modules["xbmcvfs"].File
        else:
            sys.modules["xbmcvfs"].File = self.old_file

    def test_one_read_gives_all_text_tracks_and_leaves_the_picture_track_out(self):
        found = subconvert.scan(self.video)
        self.assertEqual([0, 1], sorted(found))                     # SRT and ASS; the PGS track (3rd) is skipped
        self.assertEqual("S_TEXT/UTF8", found[0]["codec"])
        self.assertEqual(["srt 0", "srt 1", "srt 2"], [e[2] for e in found[0]["events"]])
        self.assertEqual(3, len(found[1]["events"]))
        self.assertIn("PlayResX", found[1]["header"])
        self.assertEqual(1, FakeFile.opened)

    def test_a_scan_of_one_wanted_track_matches_the_old_single_track_call(self):
        with open(self.video, "rb") as f:
            handle = FakeFile(self.video)
        info = {}
        events = subcodec.matroska_subtitle_events(subcodec._Reader(handle), 1, None, info)
        self.assertEqual(3, len(events))
        self.assertEqual("S_TEXT/ASS", info["codec"])
        self.assertIsNone(subcodec.matroska_subtitle_events(subcodec._Reader(handle), 9))

    def test_converting_a_second_track_from_the_scan_does_not_read_the_file_again(self):
        found = subconvert.scan(self.video)
        for ordinal, ext in ((0, "srt"), (1, "ass")):
            destination = os.path.join(self.dir, "out%d.%s" % (ordinal, ext))
            cues = subconvert.convert(self.video, ordinal, destination, None, None, None, None, found)
            self.assertEqual(3, cues)
            self.assertTrue(os.path.getsize(destination) > 0)
        self.assertEqual(1, FakeFile.opened)

    def test_an_empty_scan_result_is_not_read_again(self):
        self.assertEqual(0, subconvert.convert(self.video, 0, os.path.join(self.dir, "x.srt"), None, None, None, None, {}))
        self.assertEqual(0, FakeFile.opened)

    def test_stopping_ends_the_scan(self):
        self.assertIsNone(subconvert.scan(self.video, lambda: True))

    def test_progress_lines_with_part_speed_and_time_left(self):
        lines = []
        with open(self.video, "wb") as f:
            f.write(build_mkv(clusters=40))
        subconvert.scan(self.video, None, lines.append)
        self.assertTrue(lines)
        self.assertTrue(all(l.startswith("Sub converter: reading the file ") and "MB/s" in l and "left" in l
                            for l in lines), lines)
        percents = [int(l.split("file ")[1].split("%")[0]) for l in lines]
        self.assertEqual(sorted(set(percents)), percents)           # each step once, rising


if __name__ == "__main__":
    unittest.main()

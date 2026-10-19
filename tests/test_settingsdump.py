import os
import sys
import types
import unittest
import xml.etree.ElementTree as ET
from unittest import mock

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
LIB = os.path.join(ROOT, "resources", "lib")
SETTINGS_XML = os.path.join(ROOT, "resources", "settings.xml")
for path in (ROOT, LIB):
    if path not in sys.path:
        sys.path.insert(0, path)

for name in ("xbmc", "xbmcvfs", "xbmcaddon", "xbmcgui"):
    sys.modules.setdefault(name, types.ModuleType(name))
xbmc = sys.modules["xbmc"]
for attr, value in (("LOGINFO", 1), ("LOGERROR", 3), ("log", lambda *a: None),
                    ("getInfoLabel", lambda _l: "22.0")):
    if not hasattr(xbmc, attr):
        setattr(xbmc, attr, value)
if not hasattr(sys.modules["xbmcvfs"], "translatePath"):
    sys.modules["xbmcvfs"].translatePath = lambda path: path
if not getattr(sys.modules["xbmcaddon"], "Addon", None):
    sys.modules["xbmcaddon"].Addon = lambda: types.SimpleNamespace(getSetting=lambda _key: "")

import importlib.util
_spec = importlib.util.spec_from_file_location("lpm_real_settingsdump", os.path.join(LIB, "settingsdump.py"))
settingsdump = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(settingsdump)


class FakeAddon:
    def __init__(self, **values):
        self.values = values

    def getSetting(self, key):
        return self.values.get(key, "")

    def getAddonInfo(self, key):
        return {"version": "9.9.9", "path": ROOT}.get(key, "")


class SettingsDumpTests(unittest.TestCase):
    def test_the_toggle_exists_and_is_off_by_default(self):
        node = [n for n in ET.parse(SETTINGS_XML).getroot().iter("setting") if n.get("id") == "logSettings"]
        self.assertEqual(1, len(node))
        self.assertEqual("boolean", node[0].get("type"))
        self.assertEqual("false", node[0].find("default").text)

    def test_the_toggle_label_has_a_string_in_every_language(self):
        label = [n for n in ET.parse(SETTINGS_XML).getroot().iter("setting")
                 if n.get("id") == "logSettings"][0].get("label")
        folder = os.path.join(ROOT, "resources", "language")
        for lang in os.listdir(folder):
            with open(os.path.join(folder, lang, "strings.po"), encoding="utf-8") as f:
                self.assertIn('msgctxt "#%s"' % label, f.read(), lang)

    def test_every_setting_of_the_xml_is_listed_once(self):
        ids = settingsdump.setting_ids(SETTINGS_XML)
        self.assertEqual(len(ids), len(set(ids)))
        for wanted in ("enabled", "log_level", "logSettings", "condAudioSwitch", "subConverter", "regexSubFilter"):
            self.assertIn(wanted, ids)
        self.assertNotIn("checkInstallation", ids)

    def test_the_dump_shows_the_values(self):
        text = settingsdump.dump_text(FakeAddon(enabled="true", condAudioSwitch="false"), SETTINGS_XML, "22.0")
        self.assertIn("add-on version: 9.9.9, Kodi: 22.0", text)
        self.assertIn("enabled = true", text)
        self.assertIn("condAudioSwitch = false", text)

    def test_write_logs_at_info_level_whatever_the_log_level(self):
        with mock.patch.object(settingsdump.xbmcaddon, "Addon", lambda: FakeAddon(enabled="true")), \
                mock.patch.object(settingsdump.xbmc, "log") as log:
            settingsdump.write()
        message, level = log.call_args.args
        self.assertEqual(settingsdump.xbmc.LOGINFO, level)
        self.assertIn("enabled = true", message)

    def test_a_broken_settings_file_does_not_raise(self):
        self.assertEqual([], settingsdump.setting_ids(os.path.join(ROOT, "no_such_file.xml")))


if __name__ == "__main__":
    unittest.main()

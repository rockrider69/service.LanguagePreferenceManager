import os
import sys
import tempfile
import unittest

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(ROOT, "resources", "lib"))
import selfcheck


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


class SelfCheckTests(unittest.TestCase):
    def test_bytecode_folders_are_removed_everywhere(self):
        with tempfile.TemporaryDirectory() as root:
            write(os.path.join(root, "resources", "lib", "__pycache__", "a.pyc"), "x")
            write(os.path.join(root, "__pycache__", "b.pyc"), "x")
            write(os.path.join(root, "resources", "lib", "a.py"), "x")
            self.assertEqual(2, selfcheck.purge_bytecode(root))
            self.assertTrue(os.path.exists(os.path.join(root, "resources", "lib", "a.py")))
            self.assertFalse(os.path.exists(os.path.join(root, "__pycache__")))

    def test_the_fingerprint_follows_the_code(self):
        with tempfile.TemporaryDirectory() as lib:
            write(os.path.join(lib, "a.py"), "one")
            first = selfcheck.fingerprint(lib)
            self.assertEqual(first, selfcheck.fingerprint(lib))
            write(os.path.join(lib, "a.py"), "two")
            self.assertNotEqual(first, selfcheck.fingerprint(lib))

    def test_another_folder_with_the_same_addon_id_is_found(self):
        with tempfile.TemporaryDirectory() as addons:
            xml = '<?xml version="1.0"?>\n<addon\n\tid="%s"\n\tname="LPM"\n\tversion="%s"\n\t>\n</addon>\n'
            write(os.path.join(addons, "service.LanguagePreferenceManager-1.1.2", "addon.xml"), xml % ("service.languagepreferencemanager", "1.1.2"))
            write(os.path.join(addons, "service.languagepreferencemanager", "addon.xml"), xml % ("service.languagepreferencemanager", "1.1.1Beta2"))
            write(os.path.join(addons, "skin.estuary", "addon.xml"), xml % ("skin.estuary", "1.0"))
            running = os.path.join(addons, "service.LanguagePreferenceManager-1.1.2")
            found = selfcheck.other_copies(running, [addons, os.path.join(addons, "missing")])
            self.assertEqual([(os.path.join(addons, "service.languagepreferencemanager"), "1.1.1Beta2")], found)
            self.assertEqual([], selfcheck.other_copies(running, [os.path.join(addons, "skin.estuary")]))

    def make_addon(self, addons, folder, version, code="print(1)"):
        xml = '<?xml version="1.0"?>\n<addon id="service.languagepreferencemanager" version="%s">\n</addon>\n'
        write(os.path.join(addons, folder, "addon.xml"), xml % version)
        write(os.path.join(addons, folder, "resources", "lib", "a.py"), code)
        return os.path.join(addons, folder)

    def test_a_clean_installation_has_no_problems(self):
        with tempfile.TemporaryDirectory() as addons:
            here = self.make_addon(addons, "service.languagepreferencemanager", "1.1.1Beta2")
            lib = os.path.join(here, "resources", "lib")
            code = selfcheck.fingerprint(lib)
            problems, info = selfcheck.check(here, lib, [addons], "1.1.1Beta2", code)
            self.assertEqual([], problems)
            self.assertIn("1.1.1Beta2", info)

    def test_check_reports_a_second_copy_stale_bytecode_and_old_running_code(self):
        with tempfile.TemporaryDirectory() as addons:
            here = self.make_addon(addons, "service.languagepreferencemanager", "1.1.1Beta2")
            self.make_addon(addons, "service.LanguagePreferenceManager-1.1.1Beta1", "1.1.1Beta1")
            write(os.path.join(here, "resources", "lib", "__pycache__", "a.pyc"), "x")
            lib = os.path.join(here, "resources", "lib")
            problems, _info = selfcheck.check(here, lib, [addons], "1.1.1Beta2", "deadbeef")
            self.assertEqual(3, len(problems))
            self.assertTrue(any("Another copy" in p for p in problems))
            self.assertTrue(any("Compiled Python files" in p for p in problems))
            self.assertTrue(any("older code" in p for p in problems))

    def test_check_notes_a_service_that_is_not_running(self):
        with tempfile.TemporaryDirectory() as addons:
            here = self.make_addon(addons, "service.languagepreferencemanager", "1.1.1Beta2")
            problems, info = selfcheck.check(here, os.path.join(here, "resources", "lib"), [addons], None, None)
            self.assertEqual([], selfcheck.check(here, os.path.join(here, "resources", "lib"), [addons], "1.1.1beta2", None)[0])
            self.assertEqual([], problems)
            self.assertIn("not running", info)


if __name__ == "__main__":
    unittest.main()

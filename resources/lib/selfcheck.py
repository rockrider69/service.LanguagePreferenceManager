"""Start-up self-check: is the code that runs the code of this version?

A stale copy shows up in two ways: leftover bytecode (__pycache__) of an older .py file, and a second folder of the
same add-on id (an older version unzipped next to the new one), which Kodi may load instead. No import of Kodi
modules here: the functions get the paths they need, so they can be tested outside Kodi."""
import hashlib
import os
import re
import shutil

ADDON_ID = 'service.languagepreferencemanager'


def purge_bytecode(addon_path):
    """Remove every __pycache__ folder of the add-on; returns how many were removed."""
    removed = 0
    for folder, dirs, _files in os.walk(addon_path):
        for name in list(dirs):
            if name == '__pycache__':
                try:
                    shutil.rmtree(os.path.join(folder, name))
                    removed += 1
                except OSError:
                    pass
                dirs.remove(name)
    return removed


def fingerprint(lib_path):
    """Short hash of the add-on's own .py files (name and content): two installs with the same version string but
    different code have different fingerprints."""
    digest = hashlib.md5()
    try:
        names = sorted(n for n in os.listdir(lib_path) if n.endswith('.py'))
    except OSError:
        return 'unknown'
    for name in names:
        digest.update(name.encode('utf-8'))
        try:
            with open(os.path.join(lib_path, name), 'rb') as f:
                digest.update(f.read())
        except OSError:
            pass
    return digest.hexdigest()[:8]


def other_copies(addon_path, addon_dirs):
    """[(folder, version)] of the other folders under addon_dirs whose addon.xml has this add-on's id."""
    here = os.path.realpath(addon_path)
    found = []
    for base in addon_dirs:
        try:
            names = os.listdir(base)
        except OSError:
            continue
        for name in names:
            folder = os.path.join(base, name)
            if os.path.realpath(folder) == here:
                continue
            try:
                with open(os.path.join(folder, 'addon.xml'), encoding='utf-8', errors='replace') as f:
                    head = f.read(4096)
            except OSError:
                continue
            match = re.search(r'<addon\b[^>]*\bid="([^"]+)"[^>]*\bversion="([^"]+)"', head, re.S)
            if match and match.group(1).lower() == ADDON_ID:
                found.append((folder, match.group(2)))
    return found


def disk_version(addon_path):
    """The version in the addon.xml on disk, None when unreadable."""
    try:
        with open(os.path.join(addon_path, 'addon.xml'), encoding='utf-8', errors='replace') as f:
            match = re.search(r'<addon\b[^>]*\bversion="([^"]+)"', f.read(4096), re.S)
    except OSError:
        return None
    return match.group(1) if match else None


def bytecode_folders(addon_path):
    found = []
    for folder, dirs, _files in os.walk(addon_path):
        if '__pycache__' in dirs:
            found.append(os.path.join(folder, '__pycache__'))
    return found


def check(addon_path, lib_path, addon_dirs, running_version=None, running_code=None):
    """(problems, info): problems are plain sentences, empty when the installation is clean.
    running_version / running_code: what the service reported at its start (None: the service is not running)."""
    problems = []
    version = disk_version(addon_path)
    code = fingerprint(lib_path)
    for folder, other_version in other_copies(addon_path, addon_dirs):
        problems.append('Another copy of the add-on is installed: {0} (version {1}). Delete that folder and restart '
                        'Kodi.'.format(folder, other_version))
    stale = bytecode_folders(addon_path)
    if stale:
        problems.append('Compiled Python files of an older run were found ({0} folder(s)). Restart Kodi: they are '
                        'removed at start.'.format(len(stale)))
    if running_code and running_code != code:
        problems.append('Kodi is still running older code (running {0}, installed {1}). Restart Kodi.'.format(
            running_code, code))
    elif running_version and version and running_version.lower() != version.lower():     # Kodi lower-cases it
        problems.append('Kodi runs version {0}, version {1} is installed. Restart Kodi.'.format(running_version, version))
    info = 'Version {0}, code {1}\n{2}'.format(version or '?', code, addon_path)
    if not running_code:
        info += '\nThe service is not running (is the add-on enabled?).'
    return problems, info

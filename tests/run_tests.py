#!/usr/bin/env python3
"""
Menu to run the tests of this folder, and a few tools that work on files of your own (asking for the paths).

    python3 tests/run_tests.py            interactive menu
    python3 tests/run_tests.py all        run every test and exit (non-zero when one fails)
    python3 tests/run_tests.py <name>     run one test file, e.g. langcodes, settings, selfcheck (see the menu)

Nothing here needs Kodi: the unit tests replace the Kodi modules by small fakes. The tools of the second part read
real files (a Matroska video, a file name, an installed add-on folder) and ask for the paths when needed.
See notes.txt.
"""
import glob
import os
import re
import subprocess
import sys
import tempfile
import types

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
LIB = os.path.join(ROOT, 'resources', 'lib')

DESCRIPTIONS = {
    'test_langcodes': 'language codes, regions/variants, special codes (Original, Any...), languages in file names',
    'test_prefutils_integration': 'preference evaluation: audio, subtitles, conditional rules, regex filter, stored '
                                  'preferences, file-name preferences',
    'test_selfcheck': 'installation check: stale copies, compiled files, version/code fingerprint',
    'test_settings': 'settings.xml: spinner order and values, translations (.po) complete and consistent',
    'test_subconvert_srt': 'sub converter: SRT/ASS/WebVTT cue conversion',
    'test_subconverter_options': 'sub converter options: color, up to 10 audio languages / all, works with any setting',
    'test_subtitle_formats': 'subtitle format preference (SRT, ASS, WebVTT, PGS, VobSub)',
}


# --- tests ---------------------------------------------------------------------------------------------------------

def test_files():
    return sorted(os.path.splitext(os.path.basename(p))[0] for p in glob.glob(os.path.join(HERE, 'test_*.py')))


def describe(module):
    with open(os.path.join(HERE, module + '.py'), encoding='utf-8') as f:
        text = f.read()
    classes = re.findall(r'^class (\w+)\(unittest\.TestCase\)', text, re.M)
    tests = re.findall(r'^    def (test_\w+)', text, re.M)
    return classes, len(tests)


def run_unittest(args):
    """Run python -m unittest in the tests folder (a fresh process: the tests fake the Kodi modules)."""
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1')
    return subprocess.call([sys.executable, '-B', '-m', 'unittest'] + args, cwd=HERE, env=env)


def run_all():
    return run_unittest(['discover', '-s', HERE, '-p', 'test_*.py', '-v'])


def run_one_module(module, verbose=True):
    return run_unittest(['-v', module] if verbose else [module])


def run_class_or_test(module):
    classes, _ = describe(module)
    if not classes:
        print('No test class found in', module)
        return 0
    for n, c in enumerate(classes, 1):
        print('  {0}. {1}'.format(n, c))
    pick = ask('Class number (empty = back)')
    if not pick.isdigit() or not 1 <= int(pick) <= len(classes):
        return 0
    cls = classes[int(pick) - 1]
    with open(os.path.join(HERE, module + '.py'), encoding='utf-8') as f:
        text = f.read()
    body = re.split(r'^class ', text, flags=re.M)
    block = next((b for b in body if b.startswith(cls + '(')), '')
    names = re.findall(r'^    def (test_\w+)', block, re.M)
    print('  0. the whole class ({0} tests)'.format(len(names)))
    for n, t in enumerate(names, 1):
        print('  {0}. {1}'.format(n, t))
    pick = ask('Test number (empty = the whole class)')
    if pick.isdigit() and 1 <= int(pick) <= len(names):
        return run_unittest(['-v', '{0}.{1}.{2}'.format(module, cls, names[int(pick) - 1])])
    return run_unittest(['-v', '{0}.{1}'.format(module, cls)])


# --- tools on your own files ---------------------------------------------------------------------------------------

def install_fakes():
    """The few Kodi modules the add-on's libraries import; xbmcvfs.File reads a plain local file."""
    class File:
        def __init__(self, path, mode='r'):
            self.h = open(path, 'rb')

        def readBytes(self, n):
            return self.h.read(n)

        def read(self, n=-1):
            return self.h.read(n)

        def seek(self, pos, whence=0):
            return self.h.seek(pos, whence)

        def close(self):
            self.h.close()

    for name in ('xbmc', 'xbmcvfs', 'xbmcaddon', 'xbmcgui'):
        sys.modules.setdefault(name, types.ModuleType(name))
    sys.modules['xbmcvfs'].File = File
    sys.modules['xbmcvfs'].translatePath = lambda p: p
    sys.modules['xbmc'].getLocalizedString = lambda _i: ''
    sys.modules['xbmc'].sleep = lambda _ms: None
    logger = types.ModuleType('logger')
    logger.LOG_NONE, logger.LOG_ERROR, logger.LOG_INFO, logger.LOG_DEBUG = range(4)
    logger.log = lambda *_a: None
    sys.modules.setdefault('logger', logger)
    if LIB not in sys.path:
        sys.path.insert(0, LIB)


def ask(prompt, default=''):
    text = input('{0}{1}: '.format(prompt, ' [{0}]'.format(default) if default else '')).strip().strip('"\'')
    return text or default


def ask_file(prompt):
    path = os.path.expanduser(ask(prompt + ' (empty = back)'))
    if not path:
        return ''
    if not os.path.isfile(path):
        print('  Not a file:', path)
        return ''
    return path


def tool_list_subtitles():
    """Subtitle tracks (CodecIDs) the add-on reads from a Matroska video."""
    path = ask_file('Path of an .mkv video')
    if not path:
        return
    install_fakes()
    import subcodec
    codecs = subcodec.subtitle_codecs(path)
    if codecs is None:
        print('  Not a Matroska file, or the track list cannot be read.')
        return
    print('  {0} embedded subtitle track(s):'.format(len(codecs)))
    for n, codec in enumerate(codecs, 1):
        kind = ('ASS/SSA' if subcodec.is_ass(codec) else 'WebVTT' if subcodec.is_webvtt(codec)
                else 'picture (cannot be converted)' if subcodec.is_bitmap(codec) else 'text')
        print('   {0}. {1:<14} {2}  convertible: {3}'.format(n, codec, kind, subcodec.is_convertible(codec)))


def tool_convert():
    """What the sub converter writes for one subtitle track of a Matroska video."""
    path = ask_file('Path of an .mkv video')
    if not path:
        return
    install_fakes()
    import subcodec
    import subconvert
    codecs = subcodec.subtitle_codecs(path)
    if not codecs:
        print('  No readable subtitle tracks.')
        return
    for n, codec in enumerate(codecs, 1):
        print('   {0}. {1}'.format(n, codec))
    track = ask('Track number', '1')
    if not track.isdigit() or not 1 <= int(track) <= len(codecs):
        print('  Invalid track number.')
        return
    ordinal = int(track) - 1
    codec = codecs[ordinal]
    if not subcodec.is_convertible(codec):
        print('  {0} cannot be converted (picture format).'.format(codec))
        return
    language = ask('Language code for the file name', 'und')
    out = ask('Output folder', os.path.join(tempfile.gettempdir(), 'lpm_converted_test'))
    color = subconvert.normalize_color(ask('Text color for SRT output (RRGGBB; ASS keeps its styles)', 'FFFF00'))
    if not color:
        print('  Not a color, using yellow.')
        color = subconvert.DEFAULT_COLOR
    ext = 'ass' if subcodec.is_ass(codec) else 'srt'
    destination = subconvert.target_path(out, path, ordinal, language, None, ext, color)
    print('  Reading the whole file; this can take a while on a network drive...')
    cues = subconvert.convert(path, ordinal, destination, None, lambda msg: print('  ' + msg), None, color)
    if cues == 0:
        print('  Nothing converted.')
    else:
        print('  {0}: {1}'.format('Reused existing copy' if cues < 0 else '{0} cues written'.format(cues), destination))


def tool_filename():
    """Audio / subtitle languages the add-on reads from a video file name (setting: use file name)."""
    name = ask('File name or path (empty = back)')
    if not name:
        return
    install_fakes()
    import langutils
    audio, subs = langutils.filename_languages(name)
    print('  audio languages    :', audio or '-')
    print('  subtitle languages :', subs or '-')


def tool_title():
    """How a track (language tag + title) is read, and how it scores against a preference code."""
    install_fakes()
    import langutils
    tag = ask('Language tag of the track, as Kodi reports it (e.g. fre, eng, und; empty = none)', 'fre')
    title = ask('Track title (e.g. French (Parisian))')
    stream = {'language': tag, 'name': title}
    base, region = langutils.stream_tag(stream)
    print('  read as: language {0!r}, region {1!r}  (stored as {2!r})'.format(base, region, langutils.stream_code(stream)))
    while True:
        code = ask('Preference code to score against (fr-FR, fre, eng, org, any; empty = done)')
        if not code:
            return
        for kind in ('Audio', 'Subtitle'):
            print('  {0:<8} score {1}  (0 no match, 1 language, 2 language and region)'.format(
                kind, langutils.match_score(code, stream, kind)))


def tool_selfcheck():
    """The installation check of the settings button, on an add-on folder of your choice."""
    default = ROOT
    addon = os.path.expanduser(ask('Add-on folder to check', default))
    if not os.path.isdir(os.path.join(addon, 'resources', 'lib')):
        print('  Not an add-on folder (resources/lib missing):', addon)
        return
    install_fakes()
    import selfcheck
    addons_dir = ask('Folder holding your other add-ons, to look for second copies (empty = none)')
    problems, info = selfcheck.check(addon, os.path.join(addon, 'resources', 'lib'),
                                     [addons_dir] if addons_dir else [])
    print('  version on disk:', selfcheck.disk_version(addon))
    print('  problems:' if problems else '  No problems found.')
    for p in problems:
        print('   -', p)
    if info:
        print('  info:', info)


TOOLS = (
    ('Subtitle tracks of an .mkv video (codecs, convertible?)', tool_list_subtitles),
    ('Convert one subtitle track of an .mkv (what the sub converter writes)', tool_convert),
    ('Languages read from a video file name', tool_filename),
    ('Read a track title and score it against a preference (e.g. French (Parisian))', tool_title),
    ('Check an add-on installation folder (stale / second copies)', tool_selfcheck),
)


# --- menu ----------------------------------------------------------------------------------------------------------

def menu():
    modules = test_files()
    while True:
        print()
        print('=== Language Preference Manager tests ===')
        print(' a. Run ALL tests')
        for n, m in enumerate(modules, 1):
            classes, count = describe(m)
            print(' {0}. {1} ({2} tests) - {3}'.format(n, m, count, DESCRIPTIONS.get(m, '')))
        print(' c. Pick a class or a single test of a file')
        print(' Tools on your own files (asks for paths):')
        for n, (label, _) in enumerate(TOOLS, 1):
            print('  t{0}. {1}'.format(n, label))
        print(' q. Quit')
        choice = ask('Choice').lower()
        try:
            if choice in ('q', 'quit', 'exit'):
                return 0
            if choice == 'a':
                run_all()
            elif choice == 'c':
                pick = ask('File number')
                if pick.isdigit() and 1 <= int(pick) <= len(modules):
                    run_class_or_test(modules[int(pick) - 1])
            elif choice.isdigit() and 1 <= int(choice) <= len(modules):
                run_one_module(modules[int(choice) - 1])
            elif re.fullmatch(r't\d+', choice) and 1 <= int(choice[1:]) <= len(TOOLS):
                TOOLS[int(choice[1:]) - 1][1]()
            else:
                print('Unknown choice.')
        except (KeyboardInterrupt, EOFError):
            print()
            return 0
        except Exception as e:                       # a tool must never end the menu
            print('Failed: {0}: {1}'.format(type(e).__name__, e))


def main(argv):
    if len(argv) > 1:
        what = argv[1].lower()
        if what == 'all':
            return run_all()
        for m in test_files():
            if what in (m, m.replace('test_', '')):
                return run_one_module(m)
        print('Unknown test file {0!r}. Available: {1}'.format(argv[1], ', '.join(test_files())))
        return 2
    return menu()


if __name__ == '__main__':
    sys.exit(main(sys.argv))

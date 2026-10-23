import os, sys, re
sys.dont_write_bytecode = True      # no __pycache__ in the add-on folder: an old compiled copy can never be used again
import xbmc, xbmcaddon, xbmcvfs, xbmcgui
import json as simplejson

__addon__ = xbmcaddon.Addon()
__addonversion__ = __addon__.getAddonInfo('version')
__addonid__ = __addon__.getAddonInfo('id')
__addonname__ = __addon__.getAddonInfo('name')
__addonPath__ = __addon__.getAddonInfo('path')
__addonResourcePath__ = xbmcvfs.translatePath(os.path.join(__addonPath__, 'resources', 'lib'))
__addonIconFile__ = xbmcvfs.translatePath(os.path.join(__addonPath__, 'icon.png'))
__user_data_path__ = xbmcvfs.translatePath("special://profile/addon_data/service.languagepreferencemanager/")
sys.path.insert(0, __addonResourcePath__)     # this add-on's own modules first (langcodes, logger ... are common names)
import selfcheck
selfcheck.purge_bytecode(xbmcvfs.translatePath(__addonPath__))     # bytecode of an older version, before any import

from langcodes import *
from prefsettings import settings
from prefutils import LangPref_Monitor
from prefutils import LangPrefMan_Player
from logger import log, LOG_NONE, LOG_INFO, LOG_DEBUG, LOG_ERROR

settings = settings()



class Main:
    def __init__(self):
        self._init_vars()
        if not settings.service_enabled:
            log(LOG_INFO, "Service not enabled")

        self._check_installation()
        settings.readSettings()
        self._daemon()

    def _check_installation(self):
        """Log which code runs, and warn when another folder holds a copy of this add-on (an older version that
        is still installed next to this one: Kodi may load that one instead)."""
        path = xbmcvfs.translatePath(__addonPath__)
        code = selfcheck.fingerprint(__addonResourcePath__)
        log(LOG_INFO, 'Running version {0} from {1} (code {2})'.format(__addonversion__, path, code))
        # what this service runs, for the "Check installation" button of the settings (a script of its own)
        xbmcgui.Window(10000).setProperty(__addonid__ + '_version', __addonversion__)
        xbmcgui.Window(10000).setProperty(__addonid__ + '_code', code)
        try:
            copies = selfcheck.other_copies(path, [xbmcvfs.translatePath('special://home/addons'),
                                                   xbmcvfs.translatePath('special://xbmc/addons')])
        except Exception as e:
            log(LOG_DEBUG, 'Installation check failed: {0}'.format(e))
            return
        if copies:
            where = ', '.join('{0} ({1})'.format(folder, version) for folder, version in copies)
            log(LOG_ERROR, 'Another copy of {0} is installed: {1}. Running: {2} ({3}). Delete the old folder and '
                           'restart Kodi.'.format(__addonid__, where, path, __addonversion__))
            try:
                xbmcgui.Dialog().notification(__addonname__, 'Another copy is installed: delete the old folder and '
                                              'restart Kodi', xbmcgui.NOTIFICATION_WARNING, 10000)
            except Exception:
                pass

    def _init_vars(self):
        self.Monitor = LangPref_Monitor()
        self.Player = LangPrefMan_Player()
        self.Monitor.player = self.Player          # Kodi's subtitle change notifications go to the player

    def _daemon(self):
        while not self.Monitor.abortRequested():
            self.Monitor.waitForAbort(1)


def check_installation():
    """Settings button: a dialog that says whether the installation is clean (no stale code, no second copy)."""
    path = xbmcvfs.translatePath(__addonPath__)
    window = xbmcgui.Window(10000)
    problems, info = selfcheck.check(
        path, __addonResourcePath__,
        [xbmcvfs.translatePath('special://home/addons'), xbmcvfs.translatePath('special://xbmc/addons')],
        window.getProperty(__addonid__ + '_version') or None, window.getProperty(__addonid__ + '_code') or None)
    if problems:
        text = 'Problems found:\n\n' + '\n\n'.join(problems) + '\n\n' + info
    else:
        text = 'No stale versions detected and no second copy of the add-on is installed.\n\n' + info
    log(LOG_INFO, 'Installation check: {0}'.format(text.replace('\n', ' ')))
    xbmcgui.Dialog().textviewer(__addonname__ + ' - installation check', text)


# Allow this to be called as a script with parameters
if len(sys.argv) > 1 and sys.argv[1] == 'show_overrides':
    from resources.lib.override_preference_dialog import *
elif len(sys.argv) > 1 and sys.argv[1] == 'check_install':
    check_installation()
elif __name__ == "__main__":
    if xbmcgui.Window(10000).getProperty(__addonid__ + '_isrunning') == 'True':
        log(LOG_INFO, 'service {0} version {1} is already started. Doing nothing.'.format(__addonname__, __addonversion__))
    else:
        xbmcgui.Window(10000).setProperty(__addonid__ + '_isrunning', 'True')
        log(LOG_INFO, 'service {0} version {1} started'.format(__addonname__, __addonversion__))
        main = Main()
        xbmcgui.Window(10000).setProperty(__addonid__ + '_isrunning', 'False')
        xbmcgui.Window(10000).setProperty(__addonid__ + '_code', '')
        log(LOG_INFO, 'service {0} version {1} stopped'.format(__addonname__, __addonversion__))

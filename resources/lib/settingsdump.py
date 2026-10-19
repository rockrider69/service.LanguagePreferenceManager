import os
import xml.etree.ElementTree as ET

import xbmc
import xbmcaddon
import xbmcvfs

# settings without a value of their own (buttons)
_SKIPPED = ('checkInstallation', 'subConverterColorPick')


def setting_ids(settings_xml):
    """Every setting id of the add-on's settings.xml, in file order."""
    try:
        root = ET.parse(settings_xml).getroot()
    except Exception:
        return []
    ids = []
    for node in root.iter('setting'):
        setting_id = node.get('id')
        if setting_id and setting_id not in _SKIPPED and setting_id not in ids:
            ids.append(setting_id)
    return ids


def dump_text(addon, settings_xml, kodi_build=''):
    lines = ['##### LPM all settings (log settings toggle is on) #####',
             'add-on version: {0}, Kodi: {1}'.format(addon.getAddonInfo('version'), kodi_build)]
    for setting_id in setting_ids(settings_xml):
        lines.append('{0} = {1}'.format(setting_id, addon.getSetting(setting_id)))
    lines.append('##### LPM all settings #####')
    return '\n'.join(lines)


def write():
    """Writes every setting to the Kodi log, whatever the add-on's own log level is."""
    try:
        addon = xbmcaddon.Addon()
        path = xbmcvfs.translatePath(os.path.join(addon.getAddonInfo('path'), 'resources', 'settings.xml'))
        text = dump_text(addon, path, xbmc.getInfoLabel('System.BuildVersion'))
        xbmc.log('[Language Preference Manager]: ' + text, xbmc.LOGINFO)
    except Exception as e:
        xbmc.log('[Language Preference Manager]: could not write the settings to the log: {0}'.format(e), xbmc.LOGERROR)

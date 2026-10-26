import os
import xml.etree.ElementTree as ET

import xbmc
import xbmcaddon
import xbmcvfs

# settings without a value of their own (buttons)
_SKIPPED = ('checkInstallation',)


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


def option_labels(settings_xml, addon=None):
    """{setting id: {stored value: what the settings page shows for it}} for every setting with a list of choices
    (the spinners): the stored value of SubFormat1 is a number, the page shows PGS."""
    try:
        root = ET.parse(settings_xml).getroot()
    except Exception:
        return {}
    labels = {}
    for node in root.iter('setting'):
        setting_id = node.get('id')
        options = node.findall('./constraints/options/option')
        if not setting_id or not options:
            continue
        shown = {}
        for option in options:
            value, label = (option.text or '').strip(), option.get('label') or ''
            text = label
            if label.isdigit() and addon is not None and hasattr(addon, 'getLocalizedString'):
                text = addon.getLocalizedString(int(label)) or label
            shown[value] = text
        labels[setting_id] = shown
    return labels


def _shown(setting_id, value, labels):
    text = labels.get(setting_id, {}).get(value)
    return '{0} ({1})'.format(value, text) if text else value


def values(addon, settings_xml):
    """{setting id: stored value} of every setting."""
    return dict((setting_id, addon.getSetting(setting_id)) for setting_id in setting_ids(settings_xml))


_last = None                   # the values at the last dump / change: what a change is compared with


def dump_text(addon, settings_xml, kodi_build='', choices=()):
    """Every setting with its stored value (and, for a spinner, what the page shows), then `choices`: lines that
    say what the values mean together (the order of the subtitle formats ...)."""
    labels = option_labels(settings_xml, addon)
    lines = ['##### LPM all settings (log settings toggle is on) #####',
             'add-on version: {0}, Kodi: {1}'.format(addon.getAddonInfo('version'), kodi_build)]
    for setting_id in setting_ids(settings_xml):
        lines.append('{0} = {1}'.format(setting_id, _shown(setting_id, addon.getSetting(setting_id), labels)))
    lines.extend(choices)
    lines.append('##### LPM all settings #####')
    return '\n'.join(lines)


def changes_text(addon, settings_xml, choices=None):
    """The settings that differ from the last dump / change, one line each ('id = new (was old)'), then the lines
    `choices(changed ids)` gives; None when nothing differs. The values are remembered either way."""
    global _last
    now = values(addon, settings_xml)
    before, _last = _last, now
    if before is None:
        return None
    changed = [setting_id for setting_id in setting_ids(settings_xml) if now.get(setting_id) != before.get(setting_id)]
    if not changed:
        return None
    labels = option_labels(settings_xml, addon)
    lines = ['{0} = {1} (was {2})'.format(setting_id, _shown(setting_id, now[setting_id], labels),
                                         _shown(setting_id, before.get(setting_id, ''), labels))
             for setting_id in changed]
    if choices:
        lines.extend(choices(changed))
    return '##### LPM setting changed #####\n' + '\n'.join(lines) + '\n##### LPM setting changed #####'


def remember():
    """Takes the values as they are now, without writing anything (the start of the service)."""
    global _last
    try:
        addon = xbmcaddon.Addon()
        _last = values(addon, _settings_xml(addon))
    except Exception:
        _last = None


def _settings_xml(addon):
    return xbmcvfs.translatePath(os.path.join(addon.getAddonInfo('path'), 'resources', 'settings.xml'))


def write(choices=()):
    """Writes every setting to the Kodi log, whatever the add-on's own log level is."""
    global _last
    try:
        addon = xbmcaddon.Addon()
        path = _settings_xml(addon)
        text = dump_text(addon, path, xbmc.getInfoLabel('System.BuildVersion'), choices)
        _last = values(addon, path)
        xbmc.log('[Language Preference Manager]: ' + text, xbmc.LOGINFO)
    except Exception as e:
        xbmc.log('[Language Preference Manager]: could not write the settings to the log: {0}'.format(e), xbmc.LOGERROR)


def write_changes(choices=None):
    """Writes only the settings that changed since the last dump / change."""
    try:
        addon = xbmcaddon.Addon()
        text = changes_text(addon, _settings_xml(addon), choices)
        if text:
            xbmc.log('[Language Preference Manager]: ' + text, xbmc.LOGINFO)
    except Exception as e:
        xbmc.log('[Language Preference Manager]: could not write the changed settings to the log: {0}'.format(e), xbmc.LOGERROR)

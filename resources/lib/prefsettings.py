import xbmc, xbmcaddon
import re
import langutils
import settingsdump
import subformat
from prefparser import PrefParser
from resources.lib import kodi_utils
from logger import log, LOG_NONE, LOG_INFO, LOG_DEBUG, LOG_ERROR

# Signs & Songs part of the subtitle regex pattern ("S&S", "S + S", "S and S", "S.S"): the two s stand alone
_OLD_SS_PATTERN = r's[\s._+\-\/\\]*(?:&|\+)?[\s._+\-\/\\]*s|'
_SS_PATTERN = r'(?<![^\W\d_])s[\s._+\-\/\\]*(?:&|\+|and)?[\s._+\-\/\\]*s(?![^\W\d_])|'


# the profiles of the regex subtitle filter and the setting that holds the pattern of each
REGEX_PROFILES = ('anime & forced foreign subtitles', 'anime & foreign subtitles, not forced')
REGEX_PATTERN_SETTINGS = ('regexSubPattern', 'regexSubPatternNoForced')


class settings():

    def init(self):
        addon = xbmcaddon.Addon()
        self.logLevel = addon.getSetting('log_level')

        if self.logLevel and len(self.logLevel) > 0:
            self.logLevel = int(self.logLevel)
        else:
            self.logLevel = LOG_INFO
            
        self.custom_audio = []
        self.custom_subs = []
        self.custom_condsub = []

        self.service_enabled = addon.getSetting('enabled') == 'true'
    
    def __init__( self ):
        self.init()
        
    def spinner_lang(self, addon, setting_id):
        """Language spinner setting -> (english name, canonical code). Empty/unknown -> ('None', 'non')."""
        name, code = langutils.from_spinner(addon.getSetting(setting_id))
        if not code:
            log(LOG_INFO, 'Language setting {0} has no valid value ({1!r}) - treated as None'.format(
                setting_id, addon.getSetting(setting_id)))
            return ('None', langutils.NON)
        return (name, code)

    def readSettings(self):
        self.readPrefs()
        self.readCustomPrefs()
        log(LOG_DEBUG,
                 '\n##### LPM Settings #####\n' \
                 'delay: {0}ms\n' \
                 'audio on: {1}\n' \
                 'subs on: {2}\n' \
                 'cond subs on: {3}\n' \
                 'turn subs on: {4}, turn subs off: {5}\n' \
                 'signs: {15}\n' \
                 'regex sub filter: {20}\n' \
                 'blacklisted keywords (subtitles): {16}\n' \
                 'blacklisted keywords (audio): {17}\n' \
                 'audio original pref list: {19}\n' \
                 'fast subtitles display (10sec latency workaround): {18}\n' \
                 'use file name: {6}, file name regex: {7}\n' \
                 'at least one pref on: {8}\n'\
                 'audio prefs: {9}\n' \
                 'sub prefs: {10}\n' \
                 'cond sub prefs: {11}\n' \
                 'custom audio prefs: {12}\n' \
                 'custom subs prefs: {13}\n' \
                 'custom cond subs prefs: {14}\n' \
                 '##### LPM Settings #####\n'
                 .format(self.delay, self.audio_prefs_on, self.sub_prefs_on,
                         self.condsub_prefs_on, self.turn_subs_on, self.turn_subs_off,
                         self.useFilename, self.filenameRegex, self.at_least_one_pref_on,
                         self.AudioPrefs, self.SubtitlePrefs, self.CondSubtitlePrefs,
                         self.custom_audio, self.custom_subs, self.custom_condsub, self.ignore_signs_on,
                         ','.join(self.subtitle_keyword_blacklist),
                         ','.join(self.audio_keyword_blacklist),
                         self.fast_subs_display,
                         ','.join(self.audio_original_preflist),
                         '{0} (profile: {1})'.format(self.regex_sub_filter_enabled, REGEX_PROFILES[self.regex_sub_profile])
                        )
                 )
        if not getattr(self, 'settings_remembered', False):
            self.settings_remembered = True
            settingsdump.remember()                  # what a later change is compared with

    def choices_text(self, changed=None):
        """What the settings mean together, in words, for the dump: the order of the subtitle formats, the regex
        profile and its pattern. changed: the ids that changed (only the lines they affect), None for all."""
        lines = []
        if changed is None or any(i.startswith('SubFormat') or i.startswith('CondSubFormat') for i in changed):
            order = getattr(self, 'sub_format_order', [])
            lines.append('subtitle format preference: {0}'.format(
                ' > '.join(subformat.format_label(f) for f in order) if order else 'none (the first matching track)'))
        if changed is None or any(i.startswith('regexSub') for i in changed):
            if getattr(self, 'regex_sub_filter_enabled', False):
                lines.append('regex subtitle filter: on, profile "{0}", pattern {1}{2}'.format(
                    REGEX_PROFILES[getattr(self, 'regex_sub_profile', 0)], getattr(self, 'regex_sub_pattern', ''),
                    ', exclusion {0}'.format(self.regex_sub_exclusion_pattern)
                    if getattr(self, 'regex_sub_exclusion', None) else ''))
            else:
                lines.append('regex subtitle filter: off')
        return lines

    def dump_settings(self):
        # for bug reports: every setting in the log, whatever the log level (the 'logSettings' toggle). Written once
        # for each playback, when the preferences are matched; a changed setting is written by log_changed_settings
        if getattr(self, 'log_settings', False):
            settingsdump.write(self.choices_text())
        else:
            settingsdump.remember()

    def log_changed_settings(self):
        # the settings that changed since the last dump, and only those (the 'logSettings' toggle)
        if getattr(self, 'log_settings', False):
            settingsdump.write_changes(self.choices_text)
        else:
            settingsdump.remember()

    def readPrefs(self):
        addon = xbmcaddon.Addon()    

        self.service_enabled = addon.getSetting('enabled') == 'true'
        self.delay = int(addon.getSetting('delay'))
        self.audio_prefs_on = addon.getSetting('enableAudio') == 'true'
        self.audio_original_preflist_enabled = addon.getSetting('enableAudioOriginalPreflist') == 'true'
        self.audio_original_preflist = addon.getSetting('AudioOriginalPreflist')
        if self.audio_original_preflist and self.audio_original_preflist_enabled:
            self.audio_original_preflist = [c.strip() for c in self.audio_original_preflist.lower().split(',') if c.strip()]
        else:
            self.audio_original_preflist = []
        # canonical codes: 'ja', 'jpn' and 'JPN' are the same entry; 'any' accepts every original track
        self.audio_original_langs = langutils.normalize_list(self.audio_original_preflist)
        self.audio_original_any = langutils.ANY in self.audio_original_langs
        self.sub_prefs_on = addon.getSetting('enableSub') == 'true'
        self.condsub_prefs_on = addon.getSetting('enableCondSub') == 'true'
        self.cond_audio_switch = self.condsub_prefs_on and addon.getSetting('condAudioSwitch') == 'true'
        self.turn_subs_on = addon.getSetting('turnSubsOn') == 'true'
        self.turn_subs_off = addon.getSetting('turnSubsOff') == 'true'
        self.ignore_signs_on = addon.getSetting('signs') == 'true'
        self.log_settings = addon.getSetting('logSettings') == 'true'
        self.regex_sub_filter_enabled = addon.getSetting('regexSubFilter') == 'true'
        # the profile chooses which pattern is used: each has its own, and the user can add words to either
        try:
            self.regex_sub_profile = int(addon.getSetting('regexSubProfile') or 0)
        except ValueError:
            self.regex_sub_profile = 0
        if self.regex_sub_profile not in range(len(REGEX_PROFILES)):
            self.regex_sub_profile = 0
        pattern_setting = REGEX_PATTERN_SETTINGS[self.regex_sub_profile]
        self.regex_sub_pattern = addon.getSetting(pattern_setting)
        if _OLD_SS_PATTERN in self.regex_sub_pattern:
            # the old S&S part of the pattern allowed nothing between the two s, so it matched the "ss" of
            # any title (Russian, Swiss German, Classic ...): replace it in the stored setting too
            self.regex_sub_pattern = self.regex_sub_pattern.replace(_OLD_SS_PATTERN, _SS_PATTERN)
            log(LOG_INFO, 'Regex pattern: the Signs & Songs part matched any "ss" in a title, corrected to {0}'.format(
                _SS_PATTERN))
            try:
                addon.setSetting(pattern_setting, self.regex_sub_pattern)
            except Exception as e:
                log(LOG_ERROR, 'Could not store the corrected regex pattern: {0}'.format(e))
        if self.regex_sub_filter_enabled and self.regex_sub_pattern:
            try:
                self.regex_sub_filter = re.compile(self.regex_sub_pattern)
            except re.error as e:
                log(LOG_ERROR, 'Invalid regex pattern: {0} - {1}'.format(self.regex_sub_pattern, str(e)))
                self.regex_sub_filter = None
        else:
            self.regex_sub_filter = None

        # Exclusion pattern
        self.regex_sub_exclusion_enabled = addon.getSetting('regexSubExclusionEnabled') == 'true'
        self.regex_sub_exclusion_pattern = addon.getSetting('regexSubExclusion')
        if self.regex_sub_filter_enabled and self.regex_sub_exclusion_enabled and self.regex_sub_exclusion_pattern:
            try:
                self.regex_sub_exclusion = re.compile(self.regex_sub_exclusion_pattern, re.IGNORECASE)
            except re.error as e:
                log(LOG_ERROR, 'Invalid exclusion regex pattern: {0} - {1}'.format(self.regex_sub_exclusion_pattern, str(e)))
                self.regex_sub_exclusion = None
        else:
            self.regex_sub_exclusion = None

        self.subtitle_keyword_blacklist_enabled = addon.getSetting('enableSubtitleKeywordBlacklist') == 'true'
        self.subtitle_keyword_blacklist = addon.getSetting('SubtitleKeywordBlacklist')
        if self.subtitle_keyword_blacklist and self.subtitle_keyword_blacklist_enabled:
            self.subtitle_keyword_blacklist = [k for k in self.subtitle_keyword_blacklist.lower().split(',') if k.strip()]
        else:
            self.subtitle_keyword_blacklist = []
        self.audio_keyword_blacklist_enabled = addon.getSetting('enableAudioKeywordBlacklist') == 'true'
        self.audio_keyword_blacklist = addon.getSetting('AudioKeywordBlacklist')
        if self.audio_keyword_blacklist and self.audio_keyword_blacklist_enabled:
            self.audio_keyword_blacklist = [k for k in self.audio_keyword_blacklist.lower().split(',') if k.strip()]
        else:
            self.audio_keyword_blacklist = []
        self.fast_subs_display = int(addon.getSetting('FastSubsDisplay'))
        # preferred subtitle formats, best first (names of subformat.SUBTITLE_FORMATS); [] = no preference
        self.sub_format_order = []
        # the format of each of the three slots (1st, 2nd, 3rd), None for an empty slot: a conditional rule can
        # choose one of them as its own first choice (CondSubFormat01..12)
        self.sub_format_slots = [None, None, None]
        for slot, setting in enumerate(('SubFormat1', 'SubFormat2', 'SubFormat3')):
            try:
                number = int(addon.getSetting(setting) or 0)
            except ValueError:
                number = 0
            if 1 <= number <= len(subformat.SUBTITLE_FORMATS):
                self.sub_format_slots[slot] = subformat.SUBTITLE_FORMATS[number - 1]
                if subformat.SUBTITLE_FORMATS[number - 1] not in self.sub_format_order:
                    self.sub_format_order.append(subformat.SUBTITLE_FORMATS[number - 1])
        self.useFilename = addon.getSetting('useFilename') == 'true'
        self.filenameRegex = addon.getSetting('filenameRegex')
        if self.useFilename:
            self.reg = re.compile(self.filenameRegex, re.IGNORECASE)
            self.split = re.compile(r'[_|.|-]+', re.IGNORECASE)


        self.CondSubTag = 'false'

        # (english name, canonical code) per spinner slot - see langutils.from_spinner()
        # settings.xml has 6 audio spinners (AudioLang01..06): reading more only logged "no valid value" lines
        self.AudioPrefs = [(set(), [
            self.spinner_lang(addon, 'AudioLang%02d' % n) for n in range(1, 7)])]
        self.SubtitlePrefs = [(set(), [
            self.spinner_lang(addon, 'SubLang%02d' % n) + (addon.getSetting('SubForced%02d' % n),)
            for n in range(1, 4)])]
        self.CondSubtitlePrefs = [(set(), [
            self.spinner_lang(addon, 'CondAudioLang%02d' % n)
            + self.spinner_lang(addon, 'CondSubLang%02d' % n)
            + (addon.getSetting('CondSubForced%02d' % n), self.CondSubTag, self.cond_format_slot(addon, n))
            for n in range(1, 13)])]

        # These handle custom user preferences, that should be stored
        self.movieOverrides = addon.getSetting('movieOverrides') == 'true'
        self.tvShowOverrides = addon.getSetting('tvShowOverrides') == 'true'
        self.storeCustomMediaPreferences = self.movieOverrides or self.tvShowOverrides

        # the regex subtitle filter is a preference on its own (it used to be ignored here, so enabling only
        # the regex filter left the whole service idle)
        self.at_least_one_pref_on = (self.audio_prefs_on
                                    or self.sub_prefs_on
                                    or self.condsub_prefs_on
                                    or self.regex_sub_filter_enabled
                                    or self.useFilename or self.storeCustomMediaPreferences)

        log(LOG_DEBUG, 'storeCustomMediaPreferences: {0}'.format(self.storeCustomMediaPreferences))

    @staticmethod
    def cond_format_slot(addon, n):
        """The subtitle format slot conditional rule n uses first: 0 = the general order, 1..3 = the 1st / 2nd / 3rd
        preferred format of the general settings."""
        try:
            slot = int(addon.getSetting('CondSubFormat%02d' % n) or 0)
        except ValueError:
            return 0
        return slot if 0 <= slot <= 3 else 0

    def readCustomPrefs(self):
        addon = xbmcaddon.Addon()
        self.custom_audio = []
        self.custom_audio_prefs_on = False
        self.custom_subs = []
        self.custom_sub_prefs_on = False
        self.custom_condsub = []
        self.custom_condsub_prefs_on = False

        prefParser = PrefParser()
        self.custom_audio = prefParser.parsePrefString(
            addon.getSetting('CustomAudio'))
        self.custom_subs = prefParser.parsePrefString(
            addon.getSetting('CustomSub'))
        self.custom_condsub = prefParser.parsePrefString(
            addon.getSetting('CustomCondSub'))

        if len(self.custom_audio) > 0:
            self.custom_audio_prefs_on = True     
        if len(self.custom_subs) > 0:
            self.custom_sub_prefs_on = True
        if len(self.custom_condsub) >0:
            self.custom_condsub_prefs_on = True

    def is_store_user_preference_for_player(self, player):
        """
        Check if the player is playing a video and if the store user preferences is enabled for the media type of the video (e.g. movie, tv show).
        :param player: The player object
        :return: True if the player is playing a video and the store user preference is enabled for the media type, False otherwise
        """
        if not player.isPlayingVideo():
            return False

        return self.is_store_user_preference(kodi_utils.get_media_type(player))

    def is_store_user_preference(self, media_type):
        """
        Check if the user preference is supposed to be stored. That means that the custom preferences are stored for the media type.
        :param media_type:  The media type string
        :return: True if the user preference is supposed to be stored, False otherwise
        """
        if media_type is None:
            return False

        if kodi_utils.is_movie(media_type):
            log(LOG_DEBUG, 'Store user preference for movie: {0}'.format(self.movieOverrides))
            return self.movieOverrides
        elif kodi_utils.is_tv_show(media_type):
            log(LOG_DEBUG, 'Store user preference for tv show: {0}'.format(self.tvShowOverrides))
            return self.tvShowOverrides
        return False
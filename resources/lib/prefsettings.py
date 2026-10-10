import xbmc, xbmcaddon
import re
import langutils
from prefparser import PrefParser
from resources.lib import kodi_utils
from logger import log, LOG_NONE, LOG_INFO, LOG_DEBUG, LOG_ERROR

# Signs & Songs part of the subtitle regex pattern ("S&S", "S + S", "S and S", "S.S"): the two s stand alone
_OLD_SS_PATTERN = r's[\s._+\-\/\\]*(?:&|\+)?[\s._+\-\/\\]*s|'
_SS_PATTERN = r'(?<![^\W\d_])s[\s._+\-\/\\]*(?:&|\+|and)?[\s._+\-\/\\]*s(?![^\W\d_])|'


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
                         self.regex_sub_filter_enabled
                        )
                 )

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
        self.turn_subs_on = addon.getSetting('turnSubsOn') == 'true'
        self.turn_subs_off = addon.getSetting('turnSubsOff') == 'true'
        self.ignore_signs_on = addon.getSetting('signs') == 'true'
        self.sub_converter_on = addon.getSetting('subConverter') == 'true'
        self.regex_sub_filter_enabled = addon.getSetting('regexSubFilter') == 'true'
        self.regex_sub_pattern = addon.getSetting('regexSubPattern')
        if _OLD_SS_PATTERN in self.regex_sub_pattern:
            # the S&S part of the pattern up to 2.0.5 allowed nothing between the two s, so it matched the "ss" of
            # any title (Russian, Swiss German, Classic ...): replace it in the stored setting too
            self.regex_sub_pattern = self.regex_sub_pattern.replace(_OLD_SS_PATTERN, _SS_PATTERN)
            log(LOG_INFO, 'Regex pattern: the Signs & Songs part matched any "ss" in a title, corrected to {0}'.format(
                _SS_PATTERN))
            try:
                addon.setSetting('regexSubPattern', self.regex_sub_pattern)
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
        self.useFilename = addon.getSetting('useFilename') == 'true'
        self.filenameRegex = addon.getSetting('filenameRegex')
        if self.useFilename:
            self.reg = re.compile(self.filenameRegex, re.IGNORECASE)
            self.split = re.compile(r'[_|.|-]+', re.IGNORECASE)


        self.CondSubTag = 'false'

        # (english name, canonical code) per spinner slot - see langutils.from_spinner()
        self.AudioPrefs = [(set(), [
            self.spinner_lang(addon, 'AudioLang%02d' % n) for n in range(1, 13)])]
        self.SubtitlePrefs = [(set(), [
            self.spinner_lang(addon, 'SubLang%02d' % n) + (addon.getSetting('SubForced%02d' % n),)
            for n in range(1, 4)])]
        self.CondSubtitlePrefs = [(set(), [
            self.spinner_lang(addon, 'CondAudioLang%02d' % n)
            + self.spinner_lang(addon, 'CondSubLang%02d' % n)
            + (addon.getSetting('CondSubForced%02d' % n), self.CondSubTag)
            for n in range(1, 13)])]

        # These handle custom user preferences, that should be stored
        self.movieOverrides = addon.getSetting('movieOverrides') == 'true'
        self.tvShowOverrides = addon.getSetting('tvShowOverrides') == 'true'
        self.storeCustomMediaPreferences = self.movieOverrides or self.tvShowOverrides

        # the regex subtitle filter is a preference on its own (2.0 ignored it here, so enabling only
        # the regex filter left the whole service idle)
        self.at_least_one_pref_on = (self.audio_prefs_on
                                    or self.sub_prefs_on
                                    or self.condsub_prefs_on
                                    or self.regex_sub_filter_enabled
                                    or self.useFilename or self.storeCustomMediaPreferences)

        log(LOG_DEBUG, 'storeCustomMediaPreferences: {0}'.format(self.storeCustomMediaPreferences))

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
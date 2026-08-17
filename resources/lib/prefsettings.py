import xbmc, xbmcaddon
import re
from langcodes import *
from prefparser import PrefParser
from resources.lib import kodi_utils
from logger import log, LOG_NONE, LOG_INFO, LOG_DEBUG, LOG_ERROR


class settings():

    # Special language codes that should pass through languageTranslate untouched
    SPECIAL_CODES = {'org', 'unk', 'und', 'any', 'Any', 'non', 'None', 'none'}

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
        
    def safeTranslate(self, value, from_type, to_type):
        """
        Wrapper around languageTranslate that passes through special codes
        (org, unk, und, any, non) without attempting translation.
        These codes don't exist in the ISO language database and would return None.
        
        :param value: The language value to translate
        :param from_type: The source type for languageTranslate
        :param to_type: The target type for languageTranslate
        :return: The translated value, or the original special code if it's a special code
        """
        if value is None:
            return None
        # Pass special codes through untouched
        if value in self.SPECIAL_CODES:
            return value
        result = languageTranslate(value, from_type, to_type)
        # If translation fails, return the original value rather than None
        if result is None:
            log(LOG_INFO, 'Language translate returned None for value: {0} (from {1} to {2}). Using original.'.format(
                value, from_type, to_type))
            return value
        return result

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
            self.audio_original_preflist = self.audio_original_preflist.lower().split(',')
        else:
            self.audio_original_preflist = []
        self.sub_prefs_on = addon.getSetting('enableSub') == 'true'
        self.condsub_prefs_on = addon.getSetting('enableCondSub') == 'true'
        self.turn_subs_on = addon.getSetting('turnSubsOn') == 'true'
        self.turn_subs_off = addon.getSetting('turnSubsOff') == 'true'
        self.ignore_signs_on = addon.getSetting('signs') == 'true'
        self.regex_sub_filter_enabled = addon.getSetting('regexSubFilter') == 'true'
        self.regex_sub_pattern = addon.getSetting('regexSubPattern')
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
            self.subtitle_keyword_blacklist = self.subtitle_keyword_blacklist.lower().split(',')
        else:
            self.subtitle_keyword_blacklist = []
        self.audio_keyword_blacklist_enabled = addon.getSetting('enableAudioKeywordBlacklist') == 'true'
        self.audio_keyword_blacklist = addon.getSetting('AudioKeywordBlacklist')
        if self.audio_keyword_blacklist and self.audio_keyword_blacklist_enabled:
            self.audio_keyword_blacklist = self.audio_keyword_blacklist.lower().split(',')
        else:
            self.audio_keyword_blacklist = []
        self.fast_subs_display = int(addon.getSetting('FastSubsDisplay'))
        self.useFilename = addon.getSetting('useFilename') == 'true'
        self.filenameRegex = addon.getSetting('filenameRegex')
        if self.useFilename:
            self.reg = re.compile(self.filenameRegex, re.IGNORECASE)
            self.split = re.compile(r'[_|.|-]*', re.IGNORECASE)


        self.CondSubTag = 'false'

        self.AudioPrefs = [(set(), [
            (self.safeTranslate(addon.getSetting('AudioLang01'), 4, 0) ,
             self.safeTranslate(addon.getSetting('AudioLang01'), 4, 3)),
            (self.safeTranslate(addon.getSetting('AudioLang02'), 4, 0) ,
             self.safeTranslate(addon.getSetting('AudioLang02'), 4, 3)),
            (self.safeTranslate(addon.getSetting('AudioLang03'), 4, 0) ,
             self.safeTranslate(addon.getSetting('AudioLang03'), 4, 3)),
            (self.safeTranslate(addon.getSetting('AudioLang04'), 4, 0),
             self.safeTranslate(addon.getSetting('AudioLang04'), 4, 3)),
            (self.safeTranslate(addon.getSetting('AudioLang05'), 4, 0),
             self.safeTranslate(addon.getSetting('AudioLang05'), 4, 3)),
            (self.safeTranslate(addon.getSetting('AudioLang06'), 4, 0),
             self.safeTranslate(addon.getSetting('AudioLang06'), 4, 3)),
            (self.safeTranslate(addon.getSetting('AudioLang07'), 4, 0),
             self.safeTranslate(addon.getSetting('AudioLang07'), 4, 3)),
            (self.safeTranslate(addon.getSetting('AudioLang08'), 4, 0),
             self.safeTranslate(addon.getSetting('AudioLang08'), 4, 3)),
            (self.safeTranslate(addon.getSetting('AudioLang09'), 4, 0),
             self.safeTranslate(addon.getSetting('AudioLang09'), 4, 3)),
            (self.safeTranslate(addon.getSetting('AudioLang10'), 4, 0),
             self.safeTranslate(addon.getSetting('AudioLang10'), 4, 3)),
            (self.safeTranslate(addon.getSetting('AudioLang11'), 4, 0),
             self.safeTranslate(addon.getSetting('AudioLang11'), 4, 3)),
            (self.safeTranslate(addon.getSetting('AudioLang12'), 4, 0),
             self.safeTranslate(addon.getSetting('AudioLang12'), 4, 3))]
        )]
        self.SubtitlePrefs = [(set(), [
            (self.safeTranslate(addon.getSetting('SubLang01'), 4, 0) ,
             self.safeTranslate(addon.getSetting('SubLang01'), 4, 3),
             addon.getSetting('SubForced01')),
            (self.safeTranslate(addon.getSetting('SubLang02'), 4, 0) ,
             self.safeTranslate(addon.getSetting('SubLang02'), 4, 3),
             addon.getSetting('SubForced02')),
            (self.safeTranslate(addon.getSetting('SubLang03'), 4, 0) ,
             self.safeTranslate(addon.getSetting('SubLang03'), 4, 3),
             addon.getSetting('SubForced03'))]
        )]
        self.CondSubtitlePrefs = [(set(), [
            (
                self.safeTranslate(addon.getSetting('CondAudioLang01'), 4, 0),
                self.safeTranslate(addon.getSetting('CondAudioLang01'), 4, 3),
                self.safeTranslate(addon.getSetting('CondSubLang01'), 4, 0),
                self.safeTranslate(addon.getSetting('CondSubLang01'), 4, 3),
                addon.getSetting('CondSubForced01'),
                self.CondSubTag
            ),
            (
                self.safeTranslate(addon.getSetting('CondAudioLang02'), 4, 0),
                self.safeTranslate(addon.getSetting('CondAudioLang02'), 4, 3),
                self.safeTranslate(addon.getSetting('CondSubLang02'), 4, 0),
                self.safeTranslate(addon.getSetting('CondSubLang02'), 4, 3),
                addon.getSetting('CondSubForced02'),
                self.CondSubTag
            ),
            (
                self.safeTranslate(addon.getSetting('CondAudioLang03'), 4, 0),
                self.safeTranslate(addon.getSetting('CondAudioLang03'), 4, 3),
                self.safeTranslate(addon.getSetting('CondSubLang03'), 4, 0),
                self.safeTranslate(addon.getSetting('CondSubLang03'), 4, 3),
                addon.getSetting('CondSubForced03'),
                self.CondSubTag
            ),
            (
                self.safeTranslate(addon.getSetting('CondAudioLang04'), 4, 0),
                self.safeTranslate(addon.getSetting('CondAudioLang04'), 4, 3),
                self.safeTranslate(addon.getSetting('CondSubLang04'), 4, 0),
                self.safeTranslate(addon.getSetting('CondSubLang04'), 4, 3),
                addon.getSetting('CondSubForced04'),
                self.CondSubTag
            ),
            (
                self.safeTranslate(addon.getSetting('CondAudioLang05'), 4, 0),
                self.safeTranslate(addon.getSetting('CondAudioLang05'), 4, 3),
                self.safeTranslate(addon.getSetting('CondSubLang05'), 4, 0),
                self.safeTranslate(addon.getSetting('CondSubLang05'), 4, 3),
                addon.getSetting('CondSubForced05'),
                self.CondSubTag
            ),
            (
                self.safeTranslate(addon.getSetting('CondAudioLang06'), 4, 0),
                self.safeTranslate(addon.getSetting('CondAudioLang06'), 4, 3),
                self.safeTranslate(addon.getSetting('CondSubLang06'), 4, 0),
                self.safeTranslate(addon.getSetting('CondSubLang06'), 4, 3),
                addon.getSetting('CondSubForced06'),
                self.CondSubTag
            ),
            (
                self.safeTranslate(addon.getSetting('CondAudioLang07'), 4, 0),
                self.safeTranslate(addon.getSetting('CondAudioLang07'), 4, 3),
                self.safeTranslate(addon.getSetting('CondSubLang07'), 4, 0),
                self.safeTranslate(addon.getSetting('CondSubLang07'), 4, 3),
                addon.getSetting('CondSubForced07'),
                self.CondSubTag
            ),
            (
                self.safeTranslate(addon.getSetting('CondAudioLang08'), 4, 0),
                self.safeTranslate(addon.getSetting('CondAudioLang08'), 4, 3),
                self.safeTranslate(addon.getSetting('CondSubLang08'), 4, 0),
                self.safeTranslate(addon.getSetting('CondSubLang08'), 4, 3),
                addon.getSetting('CondSubForced08'),
                self.CondSubTag
            ),
            (
                self.safeTranslate(addon.getSetting('CondAudioLang09'), 4, 0),
                self.safeTranslate(addon.getSetting('CondAudioLang09'), 4, 3),
                self.safeTranslate(addon.getSetting('CondSubLang09'), 4, 0),
                self.safeTranslate(addon.getSetting('CondSubLang09'), 4, 3),
                addon.getSetting('CondSubForced09'),
                self.CondSubTag
            ),
            (
                self.safeTranslate(addon.getSetting('CondAudioLang10'), 4, 0),
                self.safeTranslate(addon.getSetting('CondAudioLang10'), 4, 3),
                self.safeTranslate(addon.getSetting('CondSubLang10'), 4, 0),
                self.safeTranslate(addon.getSetting('CondSubLang10'), 4, 3),
                addon.getSetting('CondSubForced10'),
                self.CondSubTag
            ),
            (
                self.safeTranslate(addon.getSetting('CondAudioLang11'), 4, 0),
                self.safeTranslate(addon.getSetting('CondAudioLang11'), 4, 3),
                self.safeTranslate(addon.getSetting('CondSubLang11'), 4, 0),
                self.safeTranslate(addon.getSetting('CondSubLang11'), 4, 3),
                addon.getSetting('CondSubForced11'),
                self.CondSubTag
            ),
            (
                self.safeTranslate(addon.getSetting('CondAudioLang12'), 4, 0),
                self.safeTranslate(addon.getSetting('CondAudioLang12'), 4, 3),
                self.safeTranslate(addon.getSetting('CondSubLang12'), 4, 0),
                self.safeTranslate(addon.getSetting('CondSubLang12'), 4, 3),
                addon.getSetting('CondSubForced12'),
                self.CondSubTag
            )]
        )]

        # These handle custom user preferences, that should be stored
        self.movieOverrides = addon.getSetting('movieOverrides') == 'true'
        self.tvShowOverrides = addon.getSetting('tvShowOverrides') == 'true'
        self.storeCustomMediaPreferences = self.movieOverrides or self.tvShowOverrides

        self.at_least_one_pref_on = (self.audio_prefs_on
                                    or self.sub_prefs_on
                                    or self.condsub_prefs_on
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
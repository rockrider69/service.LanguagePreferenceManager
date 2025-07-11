import xbmc, xbmcaddon
import re
from langcodes import *
from prefparser import PrefParser
from resources.lib import kodi_utils

LOG_NONE = 0
LOG_ERROR = 1
LOG_INFO = 2
LOG_DEBUG = 3
    


class settings():

    def log(self, level, msg):
        if level <= self.logLevel:
            if level == LOG_ERROR:
                l = xbmc.LOGERROR
            elif level == LOG_INFO:
                l = xbmc.LOGINFO
            elif level == LOG_DEBUG:
                l = xbmc.LOGDEBUG
            xbmc.log("[Language Preference Manager]: " + str(msg), l)

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
        
    def readSettings(self):
        self.readPrefs()
        self.readCustomPrefs()
        self.log(LOG_DEBUG,
                 '\n##### LPM Settings #####\n' \
                 'delay: {0}ms\n' \
                 'audio on: {1}\n' \
                 'subs on: {2}\n' \
                 'cond subs on: {3}\n' \
                 'turn subs on: {4}, turn subs off: {5}\n' \
                 'signs: {15}\n' \
                 'blacklisted keywords (subtitles): {16}\n' \
                 'blacklisted keywords (audio): {17}\n' \
                 'fast subtitles display (10sec latency workaround): {18}\n' \
                 'use file name: {6}, file name regex: {7}\n' \
                 'at least one pref on: {8}\n'\
                 'audio prefs: {9}\n' \
                 'sub prefs: {10}\n' \
                 'cond sub prefs: {11}\n' \
                 'custom audio prefs: {12}\n' \
                 'custom subs prefs: {13}\n'
                 'custom cond subs prefs: {14}\n'
                 '##### LPM Settings #####\n'
                 .format(self.delay, self.audio_prefs_on, self.sub_prefs_on,
                         self.condsub_prefs_on, self.turn_subs_on, self.turn_subs_off,
                         self.useFilename, self.filenameRegex, self.at_least_one_pref_on,
                         self.AudioPrefs, self.SubtitlePrefs, self.CondSubtitlePrefs,
                         self.custom_audio, self.custom_subs, self.custom_condsub, self.ignore_signs_on,
                         ','.join(self.subtitle_keyword_blacklist),
                         ','.join(self.audio_keyword_blacklist),
                         self.fast_subs_display
                        )
                 )
      
    def readPrefs(self):
      addon = xbmcaddon.Addon()    

      self.service_enabled = addon.getSetting('enabled') == 'true'
      self.delay = int(addon.getSetting('delay'))
      self.audio_prefs_on = addon.getSetting('enableAudio') == 'true'
      self.sub_prefs_on = addon.getSetting('enableSub') == 'true'
      self.condsub_prefs_on = addon.getSetting('enableCondSub') == 'true'
      self.turn_subs_on = addon.getSetting('turnSubsOn') == 'true'
      self.turn_subs_off = addon.getSetting('turnSubsOff') == 'true'
      self.ignore_signs_on = addon.getSetting('signs') == 'true'
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
          (languageTranslate(addon.getSetting('AudioLang01'), 4, 0) ,
           languageTranslate(addon.getSetting('AudioLang01'), 4, 3)),
          (languageTranslate(addon.getSetting('AudioLang02'), 4, 0) ,
           languageTranslate(addon.getSetting('AudioLang02'), 4, 3)),
          (languageTranslate(addon.getSetting('AudioLang03'), 4, 0) ,
           languageTranslate(addon.getSetting('AudioLang03'), 4, 3))]
      )]
      self.SubtitlePrefs = [(set(), [
          (languageTranslate(addon.getSetting('SubLang01'), 4, 0) ,
           languageTranslate(addon.getSetting('SubLang01'), 4, 3),
           addon.getSetting('SubForced01')),
          (languageTranslate(addon.getSetting('SubLang02'), 4, 0) ,
           languageTranslate(addon.getSetting('SubLang02'), 4, 3),
           addon.getSetting('SubForced02')),
          (languageTranslate(addon.getSetting('SubLang03'), 4, 0) ,
           languageTranslate(addon.getSetting('SubLang03'), 4, 3),
           addon.getSetting('SubForced03'))]
      )]
      self.CondSubtitlePrefs = [(set(), [
          (
              languageTranslate(addon.getSetting('CondAudioLang01'), 4, 0),
              languageTranslate(addon.getSetting('CondAudioLang01'), 4, 3),
              languageTranslate(addon.getSetting('CondSubLang01'), 4, 0),
              languageTranslate(addon.getSetting('CondSubLang01'), 4, 3),
              addon.getSetting('CondSubForced01'),
              self.CondSubTag
          ),
          (
              languageTranslate(addon.getSetting('CondAudioLang02'), 4, 0),
              languageTranslate(addon.getSetting('CondAudioLang02'), 4, 3),
              languageTranslate(addon.getSetting('CondSubLang02'), 4, 0),
              languageTranslate(addon.getSetting('CondSubLang02'), 4, 3),
              addon.getSetting('CondSubForced02'),
              self.CondSubTag
          ),
          (
              languageTranslate(addon.getSetting('CondAudioLang03'), 4, 0),
              languageTranslate(addon.getSetting('CondAudioLang03'), 4, 3),
              languageTranslate(addon.getSetting('CondSubLang03'), 4, 0),
              languageTranslate(addon.getSetting('CondSubLang03'), 4, 3),
              addon.getSetting('CondSubForced03'),
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

      self.log(LOG_DEBUG, 'storeCustomMediaPreferences: {0}'.format(self.storeCustomMediaPreferences))

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
        Check if the player is playing a video and if the store user preference is enabled for the media type of the video (e.g. movie, tv show).
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
            self.log(LOG_DEBUG, 'Store user preference for movie: {0}'.format(self.movieOverrides))
            return self.movieOverrides
        elif kodi_utils.is_tv_show(media_type):
            self.log(LOG_DEBUG, 'Store user preference for tv show: {0}'.format(self.tvShowOverrides))
            return self.tvShowOverrides
        return False
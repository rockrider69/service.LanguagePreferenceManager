from logger import log, LOG_INFO, LOG_DEBUG, LOG_ERROR
import xbmcvfs
import json as simplejson

__user_data_path__ = xbmcvfs.translatePath("special://profile/addon_data/service.languagepreferencemanager/")

from resources.lib import kodi_utils


class MediaPreferenceManager:

    def __init__(self):
        self.preferences = []

    def add_preference(self, custom_media_preference):
        if not isinstance(custom_media_preference, CustomMediaPreference):
            log(LOG_ERROR, "Cannot add non-custom media preference")
            return

        if not custom_media_preference:
            log(LOG_ERROR, "Cannot add empty custom media preference")
            return

        matching_preference = self.get_matching_preference(custom_media_preference)
        if matching_preference is not None:
            self.remove_preference(matching_preference)

        self.preferences.append(custom_media_preference)

    def remove_preference(self, custom_media_preference):
        if self.has_preference(custom_media_preference):
            self.preferences.remove(custom_media_preference)

    def has_preference(self, custom_media_preference):
        """
        Check if the custom media preference is already in the list of preferences. That is, if the same media selector is already in the list.
        :param custom_media_preference: The custom media preference to check
        :return: True if the custom media preference is already in the list, False otherwise
        """
        return self.get_matching_preference(custom_media_preference) is not None

    def get_matching_preference(self, custom_media_preference):
        """
        Get the custom media preference that matches the media selector of the given custom media preference. If no preference matches, return None.
        :param custom_media_preference: The custom media preference to match
        :return: The custom media preference that matches the media selector of the given custom media preference, or None if no preference matches
        """
        for preference in self.preferences:
            if preference.selector.is_same_media(custom_media_preference.selector):
                return preference

        return None

    def get_preference(self, player):
        """
        Get the custom media preference that applies to the playing item with the highest priority. If no preference applies, return None.
        e.g. If two preferences apply to the playing item, the one with the highest priority will be returned.
        :param player: The player to get the custom media preference for
        :return:  The custom media preference that applies to the playing item with the highest priority, or None if no preference applies
        """

        applicable_preferences = []

        for preference in self.preferences:
            log(LOG_DEBUG, "Checking preference: " + preference.selector.to_string())
            if preference.selector.applies_to_player(player):
                applicable_preferences.append(preference)

        if len(applicable_preferences) == 0:
            return None

        return max(applicable_preferences, key=lambda preference: preference.priority_index)

    def save_preferences(self):
        file_name = __user_data_path__ + "customMediaPreferences.json"

        with open(file_name, 'w') as file:
            file.write(simplejson.dumps(self.to_json(), indent=4))

    @staticmethod
    def from_file():
        file_name = __user_data_path__ + "customMediaPreferences.json"
        if xbmcvfs.exists(file_name):
            log(LOG_DEBUG, "Attempting custom media preferences from file")

            with open(file_name, 'r') as file:
                # Check if file is empty
                if not file.read(1):
                    log(LOG_DEBUG, "No custom media preferences found (empty file?)")
                    return

                file.seek(0)

                try:
                    return MediaPreferenceManager.from_json(simplejson.loads(file.read()))
                except Exception as e:
                    log(LOG_ERROR, "Failed to load custom media preferences: " + str(e))

        return MediaPreferenceManager()

    def to_json(self):
        return [preference.to_json() for preference in self.preferences]

    @staticmethod
    def from_json(json):
        custom_media_preferences = MediaPreferenceManager()
        for preference_json in json:
            custom_media_preferences.add_preference(CustomMediaPreference.from_json(preference_json))

        log(LOG_DEBUG, "Loaded " + str(len(custom_media_preferences.preferences)) + " custom media preferences")

        return custom_media_preferences


class CustomMediaPreference:

    def __init__(self):
        self.selector = None
        self.priority_index = 0
        self.audio_language = ""
        self.audio_track_id = -1
        self.subtitle_language = ""
        self.subtitle_track_id = -1
        self.enable_subtitles = False

    def apply_to_player(self, player):
        if not player.isPlayingVideo():
            return

        if self.audio_language or self.audio_track_id != -1:
            audio_track_index = self.get_audio_track_index(player)
            if audio_track_index is not None:
                player.setAudioStream(audio_track_index)

        if self.subtitle_language or self.subtitle_track_id != -1:
            subtitle_track_index = self.get_subtitle_track_index(player)
            if subtitle_track_index is not None:
                if self.enable_subtitles:
                    player.setSubtitleStream(subtitle_track_index)
                player.showSubtitles(self.enable_subtitles)

    def get_audio_track_index(self, player):
        for stream in player.audiostreams:
            if self.audio_language:
                if 'language' in stream and stream['language'] == self.audio_language:
                    return stream['index']
            if self.audio_track_id != -1:
                log(LOG_DEBUG,
                    "Failed to find audio track by language " + self.audio_language + " for file " + player.getPlayingFile() + ". Trying by index")
                if self.audio_track_id < len(player.audiostreams):
                    return self.audio_track_id
                else:
                    log(LOG_ERROR, "Audio track id " + str(
                        self.audio_track_id) + " is out of range for file " + player.getPlayingFile())

        return None

    def get_subtitle_track_index(self, player):
        for subtitle in player.subtitles:
            if self.subtitle_language:
                if subtitle['language'] == self.subtitle_language:
                    return subtitle['index']
            if self.subtitle_track_id != -1:
                log(LOG_DEBUG,
                    "Failed to find subtitle track by language " + self.subtitle_language + " for file " + player.getPlayingFile() + ". Trying by index")
                if self.subtitle_track_id < len(player.subtitles):
                    return self.subtitle_track_id
                else:
                    log(LOG_ERROR, "Subtitle track id " + str(
                        self.subtitle_track_id) + " is out of range for file " + player.getPlayingFile())
        return

    def to_json(self):
        selector_string = ""

        if self.selector:
            selector_string = self.selector.to_string()

        return {
            "selector": selector_string,
            "priority": self.priority_index,
            "audio_language": self.audio_language,
            "audio_track_id": self.audio_track_id,
            "subtitle_language": self.subtitle_language,
            "subtitle_track_id": self.subtitle_track_id,
            "enable_subtitles": self.enable_subtitles
        }

    @staticmethod
    def from_json(json):
        custom_media_preference = CustomMediaPreference()
        custom_media_preference.selector = MediaSelector.from_string(json["selector"])
        custom_media_preference.priority_index = json["priority"]
        custom_media_preference.audio_language = json["audio_language"]
        custom_media_preference.audio_track_id = json["audio_track_id"]
        custom_media_preference.subtitle_language = json["subtitle_language"]
        custom_media_preference.subtitle_track_id = json["subtitle_track_id"]
        custom_media_preference.enable_subtitles = json["enable_subtitles"]
        return custom_media_preference

    @staticmethod
    def from_player(player):
        if not player.isPlayingVideo():
            return None

        custom_media_preference = CustomMediaPreference()
        custom_media_preference.selector = MediaSelector.from_playing_item(player)

        custom_media_preference.audio_language = player.getSelectedAudioLanguage()
        custom_media_preference.audio_track_id = player.getSelectedAudioIndex()
        custom_media_preference.subtitle_language = player.getSelectedSubtitleLanguage()
        custom_media_preference.subtitle_track_id = player.getSelectedSubtitleIndex()
        custom_media_preference.enable_subtitles = player.selected_sub_enabled

        return custom_media_preference

class MediaSelector:

    def __init__(self):
        self.tv_show_name = ""
        self.file_name = ""

    def applies_to_player(self, player):
        if not player:
            return False

        if not player.isPlayingVideo():
            log(LOG_DEBUG, 'Player is not playing video, cannot apply media selector')
            return False

        playing_item = player.getPlayingItem()

        if not playing_item:
            log(LOG_DEBUG, 'No playing item found, cannot apply media selector')
            return

        video_info_tag = playing_item.getVideoInfoTag()

        if not video_info_tag:
            log(LOG_DEBUG, 'No video info tag found, cannot apply media selector')
            return

        is_tv_show = kodi_utils.is_tv_show(video_info_tag.getMediaType())
        log(LOG_DEBUG, 'Media Info: ' + video_info_tag.getMediaType() + " is_tv_show: " + str(is_tv_show))

        if is_tv_show and self.tv_show_name:
            log(LOG_DEBUG, 'Checking TV Show name: ' + self.tv_show_name + ' against ' + video_info_tag.getTVShowTitle())
            return video_info_tag.getTVShowTitle() == self.tv_show_name
        elif self.file_name:
            log(LOG_DEBUG, 'Checking file name: ' + self.file_name + ' against ' + player.getPlayingFile())
            return player.getPlayingFile() == self.file_name
        else:
            return False

    def to_string(self):
        if self.tv_show_name:
            return "tv_show:" + self.tv_show_name
        elif self.file_name:
            return "file:" + self.file_name
        else:
            return "unknown"

    def is_same_media(self, media_selector):
        return self.to_string() == media_selector.to_string()

    @staticmethod
    def from_string(s):
        if not s:
            return None

        media_info = MediaSelector()
        if s.startswith("tv_show:"):
            media_info.tv_show_name = s[8:]
        elif s.startswith("file:"):
            media_info.file_name = s[5:]
        return media_info

    @staticmethod
    def from_playing_item(player):
        media_selector = MediaSelector()
        playing_item = player.getPlayingItem()

        video_info_tag = playing_item.getVideoInfoTag()

        if not video_info_tag:
            log(LOG_ERROR, 'No video info tag found, cannot create media selector')
            return

        media_selector.tv_show_name = video_info_tag.getTVShowTitle()
        media_selector.file_name = player.getPlayingFile()

        return media_selector


media_preference_manager = MediaPreferenceManager.from_file()

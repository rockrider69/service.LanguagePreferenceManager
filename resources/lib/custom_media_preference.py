from logger import log, LOG_INFO, LOG_DEBUG, LOG_ERROR
import os
import time
import xbmcvfs
import json as simplejson

__user_data_path__ = xbmcvfs.translatePath("special://profile/addon_data/service.languagepreferencemanager/")
__preferences_file__ = __user_data_path__ + "customMediaPreferences.json"


_UNREAD = ('unread',)
# _load() results
_OK, _UNREADABLE, _INVALID = 'ok', 'unreadable', 'invalid'


def _file_state():
    """(modification time, size) of the preferences file, None when there is none."""
    try:
        st = os.stat(__preferences_file__)
        return (st.st_mtime_ns, st.st_size)
    except OSError:
        return None

from resources.lib import kodi_utils
import langutils

class MediaPreferenceManager:

    def __init__(self):
        self.preferences = []
        # this list is the file's (from_file()): it follows the file's changes - see refresh()
        self.tied = False
        # state of the file when this list was read or written (None: there was no file), _UNREAD when the
        # file could not be read (then it is read again before any change)
        self.file_state = None
        # the list is not the file's (it could not be re-read): the next save must not overwrite the file
        self.save_blocked = False
        # state of the file when it last could not be parsed (see refresh())
        self.failed_state = None

    def refresh(self):
        """
        Re-read the file when someone else changed it. The stored-preferences dialog runs in its own Python
        interpreter with its own copy of the list: without this, the service kept applying a preference deleted
        there, and its next save wrote the deleted preference back into the file.

        A file that cannot be parsed (empty, or invalid JSON) may be in the middle of a write by an older version:
        the list is kept and the file looked at again. Seen unchanged a second time, it is not being written: the
        list is kept and the next save writes it back (repairing the file). A file that cannot be opened at all
        keeps the list and blocks saving, so its content is never lost.
        :return: False when the list is not the file's (it changed but cannot be read now)
        """
        if not self.tied:
            return True
        state = _file_state()
        if state == self.file_state:
            return True
        result, fresh = MediaPreferenceManager._load()
        if result == _OK:
            log(LOG_INFO, "Custom media preferences file changed - reloading it")
            self.preferences = fresh.preferences
            self.file_state = state
            self.failed_state = None
            return True
        if result == _INVALID and state == self.failed_state:
            log(LOG_ERROR, "Custom media preferences file is not valid - the current list will replace it")
            self.file_state = state
            self.failed_state = None
            return True
        self.failed_state = state
        log(LOG_INFO, "Custom media preferences file changed but cannot be read now - keeping the current list")
        return False

    def add_preference(self, custom_media_preference):
        """Add (or replace) the preference for its media. :return: False when the file could not be read (the
        next save is then skipped, see refresh())."""
        if not isinstance(custom_media_preference, CustomMediaPreference):
            log(LOG_ERROR, "Cannot add non-custom media preference")
            return False

        if not custom_media_preference:
            log(LOG_ERROR, "Cannot add empty custom media preference")
            return False

        if not self.refresh():
            self.save_blocked = True
            return False
        matching_preference = self.get_matching_preference(custom_media_preference)
        if matching_preference is not None:
            self.preferences.remove(matching_preference)

        self.preferences.append(custom_media_preference)
        return True

    def remove_preference(self, custom_media_preference):
        """Remove the preference for the same media (the file is re-read first if someone else changed it).
        :return: False when the file could not be read (nothing removed; the caller must not save)"""
        if not self.refresh():
            return False
        matching_preference = self.get_matching_preference(custom_media_preference)
        if matching_preference is not None:
            self.preferences.remove(matching_preference)
        return True

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

        self.refresh()
        applicable_preferences = []

        for preference in self.preferences:
            log(LOG_DEBUG, "Checking preference: " + preference.selector.to_string())
            if preference.selector.applies_to_player(player):
                applicable_preferences.append(preference)

        if len(applicable_preferences) == 0:
            return None

        return max(applicable_preferences, key=lambda preference: preference.priority_index)

    def save_preferences(self):
        """Write the list. :return: True when it was written."""
        if self.save_blocked:
            # the file could not be read: writing this list would lose what the file holds
            self.save_blocked = False
            log(LOG_ERROR, "Custom media preferences not saved: the file could not be read, it is left as it is")
            return False
        content = simplejson.dumps(self.to_json(), indent=4)
        # written to a temporary file that then replaces the old one: a reader (the service or the
        # stored-preferences dialog, each in its own interpreter) never sees a half written file. Its name is
        # unique per writer, and os.open applies the umask like a normal file creation.
        temp_file = "{0}.{1}.{2}.tmp".format(__preferences_file__, os.getpid(), time.monotonic_ns())
        try:
            handle = os.open(temp_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o666)
        except OSError as e:
            log(LOG_ERROR, "Failed to save custom media preferences: " + str(e))
            return False
        try:
            with os.fdopen(handle, 'w') as file:
                file.write(content)
            try:
                os.chmod(temp_file, os.stat(__preferences_file__).st_mode & 0o777)   # keep the old permissions
            except OSError:
                pass
            # the state of what we wrote, taken before the rename (which keeps it): a file another writer moves
            # into place right after ours then still counts as a change
            st = os.stat(temp_file)
            written_state = (st.st_mtime_ns, st.st_size)
            for attempt in range(10):
                try:
                    os.replace(temp_file, __preferences_file__)
                    break
                except PermissionError:      # Windows: the other interpreter is reading the file right now
                    if attempt == 9:
                        raise
                    time.sleep(0.05)
        except OSError as e:
            log(LOG_ERROR, "Failed to save custom media preferences: " + str(e))
            try:
                os.remove(temp_file)
            except OSError:
                pass
            return False
        self.file_state = written_state
        self.failed_state = None
        return True

    @staticmethod
    def _load():
        """Read the preferences file: (_OK, manager) - a missing or empty-list file gives an empty manager -,
        (_UNREADABLE, None) when it cannot be opened, (_INVALID, None) when it is empty or not valid JSON."""
        if not xbmcvfs.exists(__preferences_file__):
            return _OK, MediaPreferenceManager()
        log(LOG_DEBUG, "Attempting custom media preferences from file")
        try:
            with open(__preferences_file__, 'r') as file:
                content = file.read()
        except OSError as e:
            log(LOG_ERROR, "Failed to read custom media preferences: " + str(e))
            return _UNREADABLE, None
        if not content.strip():
            log(LOG_DEBUG, "No custom media preferences found (empty file?)")
            return _INVALID, None
        try:
            return _OK, MediaPreferenceManager.from_json(simplejson.loads(content))
        except Exception as e:
            log(LOG_ERROR, "Failed to load custom media preferences: " + str(e))
            return _INVALID, None

    @staticmethod
    def from_file():
        """The preferences of the file. When it cannot be read, an empty list that reads the file again before
        any change (see refresh()); an empty or invalid file at start gives an empty list."""
        state = _file_state()
        result, manager = MediaPreferenceManager._load()
        if result == _OK:
            manager.tied = True
            manager.file_state = state
            return manager
        manager = MediaPreferenceManager()
        manager.tied = True
        if result == _INVALID:
            manager.file_state = state
        else:
            manager.file_state = _UNREAD
        return manager

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
        self.audio_name = ""
        self.subtitle_language = ""
        self.subtitle_track_id = -1
        self.subtitle_name = ""
        self.enable_subtitles = False

    def apply_to_player(self, player):
        """
        Apply the custom media preference to the player. This will set the audio and subtitle streams according to the preference.

        The audio part and the subtitle part are applied independently. What was really applied is recorded on the
        player (stored_audio_applied / stored_sub_applied): the regex, normal, conditional, filename and fallback logic
        must never touch a part that a stored (manually set) preference has set.

        :param player: The player to apply the custom media preference to
        :return: True if the whole custom media preference was applied, False if a part could not be applied
                 (track not found in the media). The part that was applied stays applied.
        """
        player.stored_audio_applied = False
        player.stored_sub_applied = False
        if not player.isPlayingVideo():
            return False

        set_subtitles = self.subtitle_language or self.subtitle_track_id != -1
        fully_applied = True

        if self.audio_language or self.audio_track_id != -1:
            audio_track_index = self.get_audio_track_index(player)
            if audio_track_index is not None:
                # Changing audio track causes an audio stream change call (delayed)
                # We need to ignore the change, otherwise this we might unnecessarily change the subtitles again
                if set_subtitles:
                    player.add_ignore_audio_change_index(audio_track_index)

                player.setAudioStream(audio_track_index)
                player.lpm_audio_target = audio_track_index
                player.stored_audio_applied = True
            else:
                # The stored audio track does not exist in this media: only this part falls back to the other preferences
                fully_applied = False

        if set_subtitles:
            subtitle_track_index = self.get_subtitle_track_index(player)
            if subtitle_track_index is not None:
                if self.enable_subtitles:
                    player.setSubtitleStream(subtitle_track_index)
                player.showSubtitles(self.enable_subtitles)
                player.selected_sub_enabled = bool(self.enable_subtitles)
                player.stored_sub_applied = True
            elif not self.enable_subtitles:
                # The user stored "subtitles off" and the track is not in this media: honour the "off"
                player.showSubtitles(False)
                player.selected_sub_enabled = False
                player.stored_sub_applied = True
            else:
                fully_applied = False

        return fully_applied

    def get_audio_track_index(self, player):
        """
        Get the audio track index that matches the custom media preference. If no audio track matches, return None.
        See find_track().

        :param player: The player to get the audio track index for
        :return: The audio track index that matches the custom media preference, or None if no audio track matches
        """
        return self.find_track(player, player.audiostreams, self.audio_language, self.audio_name,
                               self.audio_track_id, 'Audio')

    def get_subtitle_track_index(self, player):
        """
        Get the subtitle track index that matches the custom media preference. If no subtitle track matches, return None.
        See find_track().

        :param player: The player to get the subtitle track index for
        :return: The subtitle track index that matches the custom media preference, or None if no subtitle track matches
        """
        return self.find_track(player, player.subtitles, self.subtitle_language, self.subtitle_name,
                               self.subtitle_track_id, 'Subtitle')

    @staticmethod
    def find_track(player, streams, language, name, track_id, track_type):
        """
        Find the stored track in this media. The tracks of the stored language are searched first; the stored
        value may be in any code form (eng / en / deu / ger / eng-AU / pob ...), e.g. saved on Kodi 21 and replayed
        on Kodi 22. A track of the stored region is preferred to one of unknown region (langutils.match_score).
        When several tracks fit, the one with the stored title is taken, then the one at the stored index, then
        the first. When no track has the stored language, the track at the stored index is taken.

        :return: the track index, or None if no track matches
        """
        playing = player.getPlayingFile()
        found = langutils.best_matches(language, streams, track_type) if language else []
        if len(found) > 1 and name:
            named = [stream['index'] for stream in streams if stream['index'] in found and stream.get('name') == name]
            if named:
                log(LOG_DEBUG, f"{track_type} tracks of language {language} with the stored title {name!r}: {named}")
                found = named

        if len(found) == 1:
            log(LOG_DEBUG, f"Found {track_type} track by language {language} for file {playing}")
            return found[0]
        if found:
            if track_id in found:
                log(LOG_DEBUG, f"Multiple {track_type} tracks found for language {language} for file {playing}, "
                               f"using the stored index {track_id}")
                return track_id
            log(LOG_DEBUG, f"Multiple {track_type} tracks found for language {language} for file {playing}. Picking first.")
            return found[0]

        if track_id != -1:
            log(LOG_DEBUG, f"Failed to find {track_type} track by language {language} for file {playing}. Trying by index")
            if track_id < len(streams):
                log(LOG_DEBUG, f"Found {track_type} track by index {track_id} for file {playing}")
                return track_id
            log(LOG_ERROR, f"{track_type} track id {track_id} is out of range for file {playing}")
        return None

    def to_json(self):
        """
        Convert the custom media preference to a JSON object. The selector is converted to a string separately.
        Counterpart to from_json.
        :return: The custom media preference as a JSON object
        """
        selector_string = ""

        if self.selector:
            selector_string = self.selector.to_string()

        return {
            "selector": selector_string,
            "priority": self.priority_index,
            "audio_language": self.audio_language,
            "audio_track_id": self.audio_track_id,
            "audio_name": self.audio_name,
            "subtitle_language": self.subtitle_language,
            "subtitle_track_id": self.subtitle_track_id,
            "subtitle_name": self.subtitle_name,
            "enable_subtitles": self.enable_subtitles
        }

    @staticmethod
    def from_json(json):
        """
        Create a custom media preference from a JSON object. The selector is created from a string separately.
        Counterpart to to_json.
        :param json: The JSON object to create the custom media preference from
        :return: The custom media preference created from the JSON object
        """
        custom_media_preference = CustomMediaPreference()
        custom_media_preference.selector = MediaSelector.from_string(json["selector"])
        custom_media_preference.priority_index = json["priority"]
        custom_media_preference.audio_language = json["audio_language"]
        custom_media_preference.audio_track_id = json["audio_track_id"]
        custom_media_preference.audio_name = json.get("audio_name", "")
        custom_media_preference.subtitle_language = json["subtitle_language"]
        custom_media_preference.subtitle_track_id = json["subtitle_track_id"]
        custom_media_preference.subtitle_name = json.get("subtitle_name", "")
        custom_media_preference.enable_subtitles = json["enable_subtitles"]
        return custom_media_preference

    @staticmethod
    def from_player(player):
        """
        Create a custom media preference from the currently playing item of the player. The selector is created from the playing item.
        :param player: The player to create the custom media preference from
        :return: The custom media preference created from the player or None if the player is not playing a video
        """

        if not player.isPlayingVideo():
            return None

        custom_media_preference = CustomMediaPreference()
        custom_media_preference.selector = MediaSelector.from_playing_item(player)

        # the language with its region when the track tells it (pob, eng-AU), and the track title
        custom_media_preference.audio_language = (langutils.stream_code(getattr(player, 'selected_audio_stream', None))
                                                  or player.getSelectedAudioLanguage())
        custom_media_preference.audio_name = (getattr(player, 'selected_audio_stream', None) or {}).get('name', '') or ''
        # If the selected audio track is flagged as original, store "org" as the language
        if hasattr(player, 'selected_audio_stream') and player.selected_audio_stream and \
                player.selected_audio_stream.get('isoriginal', False):
            custom_media_preference.audio_language = "org"
        custom_media_preference.audio_track_id = player.getSelectedAudioIndex()

        custom_media_preference.subtitle_language = (langutils.stream_code(getattr(player, 'selected_sub', None))
                                                     or player.getSelectedSubtitleLanguage())
        custom_media_preference.subtitle_name = (getattr(player, 'selected_sub', None) or {}).get('name', '') or ''
        # If the selected subtitle track has "original" or "unknown" in its name, store the special code
        if hasattr(player, 'selected_sub') and player.selected_sub:
            sub_name_lower = player.selected_sub.get('name', '').lower()
            if "original" in sub_name_lower:
                custom_media_preference.subtitle_language = "org"
            elif "unknown" in sub_name_lower or player.selected_sub.get('language', '') == "unk":
                custom_media_preference.subtitle_language = "unk"
        custom_media_preference.subtitle_track_id = player.getSelectedSubtitleIndex()
        custom_media_preference.enable_subtitles = player.selected_sub_enabled

        return custom_media_preference


class MediaSelector:
    """
    A media selector is used to identify and store a specific media item. It can be created from a playing item or restored from a string.
    MediaSelector supports two types of media selection:
    - TV Show: The TV show name is used to identify the media item.
    - File: The file name is used to identify the media item.
    """

    def __init__(self):
        self.tv_show_name = ""
        self.file_name = ""

    def applies_to_player(self, player):
        """
        Check if the media selector applies to the player. That is, if the playing item of the player matches the media selector.
        :param player: The player to check the media selector against
        :return: True if the media selector applies to the player, False otherwise
        """
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
            log(LOG_DEBUG,
                'Checking TV Show name: ' + self.tv_show_name + ' against ' + video_info_tag.getTVShowTitle())
            return video_info_tag.getTVShowTitle() == self.tv_show_name
        elif self.file_name:
            log(LOG_DEBUG, 'Checking file name: ' + self.file_name + ' against ' + player.getPlayingFile())
            return player.getPlayingFile() == self.file_name
        else:
            return False

    def to_string(self):
        """
        Convert the media selector to a string. The string is used to serialize the media selector.
        Counterpart to from_string.
        :return: The media selector as a string
        """
        type_name = self.get_type_name()
        display_name = self.get_display_name()
        return type_name + ":" + display_name

    def get_display_name(self):
        """
        Get the display name of the media selector. The display name is used to identify the media selector in the UI.
        :return: The display name of the media selector
        """
        if self.tv_show_name:
            return self.tv_show_name
        elif self.file_name:
            return self.file_name
        else:
            return "Unknown Media Selector"

    def get_type_name(self):
        """
        Get the type name of the media selector. The type name is used to identify the media selector type.
        :return: The type name of the media selector
        """
        if self.tv_show_name:
            return "tv_show"
        elif self.file_name:
            return "file"
        else:
            return "unknown"

    def is_same_media(self, media_selector):
        """
        Check if the media selector is the same as the given media selector. That is, if the media selector serializes to the same string.
        :param media_selector: The media selector to compare to
        :return: True if the media selector is the same as the given media selector, False otherwise
        """
        return self.to_string() == media_selector.to_string()

    @staticmethod
    def from_string(s):
        """
        Create a media selector from a string.
        Counterpart to to_string.
        :param s: The string to create the media selector from
        :return: The media selector created from the string
        """
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
        """
        Create a media selector from the playing item of the player. The media selector is created based on the media type of the playing item.
        If the media type is a TV show, the TV show name is used. If the media type is a movie, the file name is used.
        :param player: The player to create the media selector from
        :return: The media selector created from the playing item or None if the player is not playing a video
        """
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
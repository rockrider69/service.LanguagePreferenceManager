import os, sys, re
import threading
import time

import xbmc, xbmcaddon, xbmcvfs

from custom_media_preference import media_preference_manager, CustomMediaPreference
from logger import log, LOG_NONE, LOG_INFO, LOG_DEBUG, LOG_ERROR

import json as simplejson

import langutils
import subcodec
import subconvert

__user_data_path__ = xbmcvfs.translatePath("special://profile/addon_data/service.languagepreferencemanager/")
from prefsettings import settings

settings = settings()

class LangPref_Monitor(xbmc.Monitor):

    def __init__(self):
        xbmc.Monitor.__init__(self)

    def onSettingsChanged(self):
        settings.init()
        settings.readSettings()

class LangPrefWatcher(threading.Thread):
    """
    A thread that periodically checks for subtitle changes.
    """

    def __init__(self, player, check_interval=10):
        super().__init__()
        self.player = player
        self.check_interval = check_interval

        # Event to stop the thread gracefully
        self._stop_event = threading.Event()

        # Ensures the thread exits when the program ends
        self.daemon = True

    def run(self):
        """
        This method runs in the background and periodically checks for subtitle changes.
        It sleeps in short slices and honours Kodi's abort request, so Kodi never hangs on exit (1.0.8 fix).
        """
        monitor = xbmc.Monitor()
        while not self._stop_event.is_set() and not monitor.abortRequested():
            try:
                if self.player.isPlayingVideo():
                    self.player.detect_subtitle_change()
            except Exception as e:
                log(LOG_ERROR, 'Subtitle watcher error: {0}'.format(e))
            waited = 0.0
            while waited < self.check_interval and not self._stop_event.is_set():
                if monitor.waitForAbort(0.5):
                    return
                waited += 0.5

    def stop(self):
        """ Method to stop the thread gracefully """
        self._stop_event.set()
        if self.is_alive() and threading.current_thread() is not self:
            self.join(timeout=2)


class LangPrefMan_Player(xbmc.Player):

    def __init__(self):
        self.LPM_initial_run_done = False
        self.selected_sub_enabled = False
        # regex subtitle filter hit on the initial run: it keeps priority over conditional subtitles when
        # the audio track is changed later on (conditional subs are re-evaluated on every audio change)
        self.regex_sub_selected = False
        # audio index LPM itself switched to - that switch must not be stored as a manual user override
        self.lpm_expected_audio_index = None
        # audio index LPM switched to on the initial run (audio / filename / stored preference), until Kodi confirms it
        self.lpm_audio_target = None
        # LPM's own audio switch was confirmed before the initial run ended: re-check the conditional subtitles then
        self.cond_recheck_pending = False
        # parts of a stored (manually set) preference that were applied on this playback - see apply_to_player()
        self.stored_audio_applied = False
        self.stored_sub_applied = False
        # subtitle files next to the playing video: (playing file, [langutils.subtitle_file_tag() results])
        self.external_sub_files = (None, [])
        self.sub_codecs = (None, None)            # (playing file, embedded subtitle CodecIDs or None)
        # sub converter: a converted subtitle is being made / selected (LPM's own change, never a user's)
        self.sub_converting = False
        self.sub_convert_quiet_until = 0
        # Kodi's subtitle list and the languages read for its external streams: (key, {index: tag})
        self.external_sub_tags = (None, {})
        self.genres_and_tags = set()

        self.ignore_audio_change_index_list = []

        settings.readSettings()
        xbmc.Player.__init__(self)

        if settings.storeCustomMediaPreferences:
            # Start the LangPrefWatcher thread. This thread will periodically check for subtitle changes.
            # This is because onAVChange does not get called when the subtitle stream changes.
            self.lang_pref_watcher = LangPrefWatcher(self, check_interval=10)
            self.lang_pref_watcher.start()

    def add_ignore_audio_change_index(self, index):
        """
        Adds an audio stream index to the ignore list.
        This means that the audio stream will be ignored for changes and preference re-evaluation will not be done.
        After one matching change based on index, the audio stream will be considered again.
        :param index: The index of the audio stream to ignore.
        """
        if index not in self.ignore_audio_change_index_list:
            self.ignore_audio_change_index_list.append(index)
            log(LOG_DEBUG, f"Audio stream index {index} added to ignore list.")

    def remove_ignore_audio_change_index(self, index):
        """
        Removes an audio stream index from the ignore list.
        This means that the audio stream will be considered for changes again and preference re-evaluation will be done.
        :param index: The index of the audio stream to remove from the ignore list.
        """
        if index in self.ignore_audio_change_index_list:
            self.ignore_audio_change_index_list.remove(index)
            log(LOG_DEBUG, f"Audio stream index {index} removed from ignore list.")

    def is_ignore_audio_change_index(self, index):
        """
        Checks if an audio stream index is in the ignore list.
        This means that the audio stream will be ignored for changes and preference re-evaluation will not be done.
        :param index: The index of the audio stream to check.
        :return: True if the index is in the ignore list, False otherwise.
        """
        return index in self.ignore_audio_change_index_list

    def onPlayBackPaused(self):
        """ Will be called when [user] stops Kodi playing a file """
        log(LOG_DEBUG, 'Player: [onPlayBackPaused] called')
        self.detect_subtitle_change()

    def onPlayBackResumed(self):
        """ Will be called when [user] stops Kodi playing a file """
        log(LOG_DEBUG, 'Player: [onPlayBackResumed] called')
        self.detect_subtitle_change()

    def onPlayBackStarted(self):
        self.regex_sub_selected = False
        self.lpm_expected_audio_index = None
        self.lpm_audio_target = None
        self.cond_recheck_pending = False
        self.stored_audio_applied = False
        self.stored_sub_applied = False
        self.external_sub_files = (None, [])     # the subtitle files may have changed since the last playback
        self.sub_codecs = (None, None)
        self.external_sub_tags = (None, {})
        if settings.service_enabled and settings.at_least_one_pref_on:
            log(LOG_DEBUG, 'New AV Playback initiated - Resetting LPM Initial Flag')
            self.LPM_initial_run_done = False

    def onAVStarted(self):
        if settings.service_enabled and settings.at_least_one_pref_on and self.isPlayingVideo():
            log(LOG_DEBUG, 'Playback started')
            self.audio_changed = False
            # switching an audio track to early leads to a reopen -> start at the beginning
            if settings.delay > 0:
                log(LOG_DEBUG, "Delaying preferences evaluation by {0} ms".format(settings.delay))
                xbmc.sleep(settings.delay)
            log(LOG_DEBUG, 'Getting video properties')
            if not self.getDetails():
                return

            # If the user has enabled to store preferences (that is manually overriden preferences) for the player, we willl check for that here
            if settings.is_store_user_preference_for_player(self):
                log(LOG_DEBUG, 'Media preference storage enabled for current media. Checking for custom preferences...')
                custom_preference = media_preference_manager.get_preference(self)

                if custom_preference is not None:
                    log(LOG_INFO, 'Custom media preferences found for current media - Applying them...')
                    log(LOG_INFO, '       ... Audio {0} Subtitles {1} Enabled {2} .'.format(custom_preference.audio_language,
                                                                                        custom_preference.subtitle_language,
                                                                                        custom_preference.enable_subtitles))
                    if not custom_preference.apply_to_player(self):
                        log(LOG_INFO,
                            'Custom media preferences only partly applicable to current media. The applied part is kept, the rest falls back to the other preferences...')
                        self.evalPrefs()
                else:
                    self.evalPrefs()
            else:
                self.evalPrefs()

            # Adopt what is selected NOW as the baseline for user-change detection, so tracks picked by LPM
            # itself are never mistaken for (and stored as) manual user overrides.
            self.refresh_subtitle_baseline()
            self.LPM_initial_run_done = True

            # Kodi already confirmed LPM's own audio switch, so no later onAVChange will re-check the conditional
            # subtitles for the new audio track: do it now, as that onAVChange would have done
            if self.cond_recheck_pending:
                self.cond_recheck_pending = False
                if settings.condsub_prefs_on:
                    log(LOG_DEBUG, 'Audio switch already done - reviewing Conditional Subtitles rules now')
                    # Kodi plays the new track already: no extra wait, and the fast-subs workaround runs only if
                    # this changes the subtitle
                    self.audio_changed = False
                    before = (self.getSelectedSubtitleIndex(), self.selected_sub_enabled)
                    self.evalPrefs(fast_subs=False)
                    self.refresh_subtitle_baseline()
                    # a newly selected subtitle gets the start's workaround; the resume rewind only if subtitles
                    # were off at the start (else the start rewound already)
                    if self.selected_sub_enabled and (self.getSelectedSubtitleIndex(), True) != before:
                        self.fast_subs_workaround(initial_run=not before[1])

    def onAVChange(self):
        """
        This method is called when the audio or video stream changes. It is not called when the subtitle stream changes.
        :return: None
        """
        log(LOG_DEBUG, 'onAVChange detected')
        if self.LPM_initial_run_done and settings.service_enabled and settings.at_least_one_pref_on and self.isPlayingVideo():
            log(LOG_DEBUG, 'AVChange detected - Checking possible change of audio track...')
            self.audio_changed = False

            if settings.delay > 0:
                log(LOG_DEBUG, "Delaying preferences evaluation by {0} ms".format(settings.delay))
                xbmc.sleep(settings.delay)

            # 1.0.8: there may be no current audio stream yet - never index the cached dict directly
            previous_audio_index = self.getSelectedAudioIndex()
            previous_audio_language = self.getSelectedAudioLanguage()
            # Kodi 22 also fires onAVChange when the SUBTITLE changes, and the getDetails() below refreshes the cache
            # the 10 s watcher compares against - so remember the subtitle state here to still catch user changes.
            previous_sub_index = self.getSelectedSubtitleIndex()
            previous_sub_language = self.getSelectedSubtitleLanguage()
            previous_sub_enabled = self.selected_sub_enabled

            log(LOG_DEBUG, 'Getting video properties')
            if not self.getDetails():
                return

            log(LOG_DEBUG, 'Subtitle enabled: {0}'.format(self.selected_sub_enabled))

            new_audio_index = self.getSelectedAudioIndex()

            if self.is_ignore_audio_change_index(new_audio_index):
                log(LOG_DEBUG, 'Audio track index {0} is in the ignore list. Skipping preference evaluation.'.format(new_audio_index))
                self.remove_ignore_audio_change_index(new_audio_index)
                return

            # An audio switch made by LPM itself (audio / filename preferences) must still re-trigger the
            # conditional subtitle rules, but it is not a user choice and must never be stored as one.
            lpm_initiated = (self.lpm_expected_audio_index is not None
                             and new_audio_index == self.lpm_expected_audio_index)
            if lpm_initiated:
                self.lpm_expected_audio_index = None

            if new_audio_index != previous_audio_index:
                log(LOG_INFO, 'Audio track changed from {0} to {1}. Reviewing Conditional Subtitles rules...'.format(
                    previous_audio_language, self.getSelectedAudioLanguage()))

                if settings.is_store_user_preference_for_player(self) and not lpm_initiated:
                    custom_preference = CustomMediaPreference.from_player(self)
                    media_preference_manager.add_preference(custom_preference)
                    media_preference_manager.save_preferences()

                self.evalPrefs()
                self.refresh_subtitle_baseline()
            else:
                self._check_subtitle_change(previous_sub_index, previous_sub_enabled, previous_sub_language)

    def detect_subtitle_change(self):
        """
        This method detects if the subtitle track has changed and stores the new preference if it has.
        :return: None
        """
        if self.LPM_initial_run_done and settings.service_enabled and settings.at_least_one_pref_on and self.isPlayingVideo():
            log(LOG_DEBUG, 'Running subtitle change detect')
            previous_sub_index = self.getSelectedSubtitleIndex()
            previous_sub_language = self.getSelectedSubtitleLanguage()
            previous_enabled_sub = self.selected_sub_enabled

            if not self.getDetails():
                return

            self._check_subtitle_change(previous_sub_index, previous_enabled_sub, previous_sub_language)

    def _check_subtitle_change(self, previous_sub_index, previous_enabled_sub, previous_sub_language):
        """Compare the (freshly read) subtitle state with the previous one; store a manual change."""
        if time.time() < self.sub_convert_quiet_until:
            log(LOG_DEBUG, 'Subtitle change ignored: the sub converter selected its own subtitle')
            return
        if self.getSelectedSubtitleIndex() != previous_sub_index or self.selected_sub_enabled != previous_enabled_sub:
            log(LOG_DEBUG, 'Subtitle track changed from {0} to {1}'.format(previous_sub_language,
                                                                           self.getSelectedSubtitleLanguage()))

            if settings.is_store_user_preference_for_player(self):
                custom_preference = CustomMediaPreference.from_player(self)
                media_preference_manager.add_preference(custom_preference)
                media_preference_manager.save_preferences()

    def stream_matches_language(self, code, stream, track_type='Audio'):
        """Thin wrapper: all language matching lives in langutils (2/3 letter codes, B/T variants, specials)."""
        return langutils.stream_matches_language(code, stream, track_type)

    def best_matches(self, code, name, streams, track_type, accept):
        """Indexes of the accepted streams that fit code best (langutils.match_score); streams whose language
        equals the preference's name are taken when no code matches. First stream first."""
        accepted = [st for st in streams or [] if accept(st)]
        found = langutils.best_matches(code, accepted, track_type)
        if not found:
            found = [st['index'] for st in accepted if name == st.get('language')]
        return found

    def subtitle_filter(self, forced, prefix, signs_only=False):
        """Filter for subtitle candidates: not blacklisted, no Signs&Songs track while that toggle is on, and the
        forced flag as asked ('true' / 'false'); with signs_only, only Signs&Songs tracks (the -ss tag)."""
        def accept(sub):
            sub_name = sub.get('name', '') or ''
            if self.isInBlacklist(sub_name, 'Subtitle'):
                log(LOG_INFO, '{0} : one subtitle track is found matching Keyword Blacklist : {1}. Skipping it.'.format(
                    prefix, ','.join(settings.subtitle_keyword_blacklist)))
                return False
            if settings.ignore_signs_on and self.isSignsSub(sub_name):
                log(LOG_INFO, '{0} : ignore_signs toggle is on and one such subtitle track is found. Skipping it.'.format(
                    prefix))
                return False
            if signs_only:
                return self.isSignsSub(sub_name)
            return self.testForcedFlag(forced, sub_name, sub.get('isforced', False))
        return accept

    def _show_subs(self, enabled):
        """showSubtitles() that also keeps our cached state truthful (it was stale after LPM's own change)."""
        self.showSubtitles(enabled)
        self.selected_sub_enabled = bool(enabled)

    def refresh_subtitle_baseline(self):
        """
        Re-read what Kodi has selected right now and adopt it as the baseline of detect_subtitle_change().
        The cached audio stream is kept while an audio switch made by LPM itself is still pending: onAVChange compares
        against it to recognise that switch. Once Kodi plays the track LPM chose, that track is the baseline, so a
        later user switch back to the track Kodi had started with is still seen as a change (and stored).
        """
        try:
            xbmc.sleep(500)
            saved_audio = getattr(self, 'selected_audio_stream', None)
            if not self.getDetails():
                return
            target = self.lpm_audio_target
            if target is not None and self.getSelectedAudioIndex() == target:
                log(LOG_DEBUG, 'Audio track {0} chosen by LPM is playing - new audio baseline'.format(target))
                self.lpm_audio_target = None
                self.remove_ignore_audio_change_index(target)
                if self.lpm_expected_audio_index == target:
                    self.lpm_expected_audio_index = None
                    self.cond_recheck_pending = not self.LPM_initial_run_done
            elif saved_audio is not None:
                self.selected_audio_stream = saved_audio
        except Exception as e:
            log(LOG_DEBUG, 'refresh_subtitle_baseline failed: {0}'.format(e))

    def evalPrefs(self, fast_subs=True):
        
        # Separate flag for regex filter to allow conditional subs fallback
        regex_sub_matched = False
        sub_preference_matched = False
        # conditional rules explicitly decided "no subtitles" - the final fallback must not undo that
        cond_decided_no_subs = False
        # What a stored (manually set) preference applied on this playback is never touched by the regex,
        # normal, conditional, filename or fallback logic: stored preferences are the only thing that outranks
        # the regex filter. If a stored preference was only partly applicable, only the other part falls through.
        protect_audio = self.stored_audio_applied
        protect_sub = self.stored_sub_applied
        if protect_audio or protect_sub:
            log(LOG_INFO, 'Stored media preference applied (audio: {0}, subtitles: {1}) - protected from the other preferences'.format(
                protect_audio, protect_sub))

        # SUBTITLE PRIORITY (initial run):
        #   1. regex subtitle filter (if enabled)                   - nothing below may override a regex hit
        #   2. conditional subtitle rules (if enabled)              - used when the regex found nothing
        #   3. subtitle tag in the file name ("Use filename")       - lowest preference, only if nothing above acted
        #   4. default subtitle, else the first valid one           - when nothing above selected a track
        # (the audio tag of the file name likewise only applies when the audio preferences matched nothing)
        # The normal subtitle preferences rank below the conditional rules (as in 1.0.x) and are skipped
        # entirely when the regex filter matched.
        if settings.regex_sub_filter_enabled and not self.LPM_initial_run_done and not protect_sub:
            regex_sub_index = self.evalRegexSubPrefs()
            if regex_sub_index >= 0:
                self.setSubtitleStream(regex_sub_index)
                regex_sub_matched = True
                self.regex_sub_selected = True
                sub_preference_matched = True
                if settings.turn_subs_on:
                    log(LOG_INFO, 'Regex subtitle: enabling subs')
                    self._show_subs(True)
            else:
                log(LOG_INFO, 'Regex subtitle: No match found, will check conditional subtitle preferences, then the default/first valid subtitle')

        # Filename-based preferences (tags like .audiostream-1.subtitle-2 in the file name).
        # LOWEST priority: only read here; the audio tag is applied after the audio preferences and the subtitle
        # tag after regex / normal / conditional subtitle preferences - and only if those selected nothing.
        filename_audio = -1
        filename_sub = -1
        if settings.useFilename and not self.LPM_initial_run_done:
            filename_audio, filename_sub = self.evalFilenamePrefs()

        # Audio preferences
        audio_pref_matched = False
        if settings.audio_prefs_on and not self.LPM_initial_run_done and not protect_audio:
            if settings.custom_audio_prefs_on:
                trackIndex = self.evalAudioPrefs(settings.custom_audio)
            else:
                trackIndex = self.evalAudioPrefs(settings.AudioPrefs)

            if trackIndex == -2:
                log(LOG_INFO, 'Audio: None of the preferred languages is available')
            else:
                audio_pref_matched = True          # -1 = the selected track already matches a preference
                if trackIndex >= 0:
                    self.setAudioStream(trackIndex)
                    self.lpm_expected_audio_index = trackIndex
                    self.lpm_audio_target = trackIndex
                    self.audio_changed = True

        # Filename audio tag - lowest priority: only if no audio preference matched
        if filename_audio >= 0 and not protect_audio:
            if audio_pref_matched:
                log(LOG_INFO, 'Filename preference: audio track {0} ignored - an audio preference matched and has priority'.format(filename_audio))
            elif filename_audio < len(self.audiostreams):
                log(LOG_INFO, 'Filename preference: Match, selecting audio track {0}'.format(filename_audio))
                self.setAudioStream(filename_audio)
                self.lpm_expected_audio_index = filename_audio
                self.lpm_audio_target = filename_audio
                self.audio_changed = True

        # SUBTITLE PREFERENCES — evaluate if sub_prefs_on is enabled, regardless of turn_subs_on setting
        if settings.sub_prefs_on and not regex_sub_matched and not self.LPM_initial_run_done and not protect_sub:
            if settings.custom_sub_prefs_on:
                trackIndex = self.evalSubPrefs(settings.custom_subs)
            else:
                trackIndex = self.evalSubPrefs(settings.SubtitlePrefs)

            if trackIndex == -2:
                log(LOG_INFO, 'Subtitle: None of the preferred languages is available')
                if settings.turn_subs_off:
                    log(LOG_INFO, 'Subtitle: disabling subs')
                    self._show_subs(False)
            elif trackIndex == -1:
                # the subtitle Kodi already selected matches: that is a match like any other (1.0.x switched it on
                # too) - the filename tag and the fallback below must not replace it
                sub_preference_matched = True
                if settings.turn_subs_on and not self.selected_sub_enabled:
                    log(LOG_INFO, 'Subtitle: the selected subtitle matches the preference - enabling subs')
                    self._show_subs(True)
            elif trackIndex >= 0:
                self.setSubtitleStream(trackIndex)
                sub_preference_matched = True
                # Enable subtitles on match IF turn_subs_on is enabled OR if already enabled
                if settings.turn_subs_on or self.selected_sub_enabled:
                    if not self.selected_sub_enabled:
                        log(LOG_INFO, 'Subtitle: enabling subs (preference match, turn_subs_on={0})'.format(settings.turn_subs_on))
                        self._show_subs(True)
        elif settings.sub_prefs_on and regex_sub_matched:
            log(LOG_DEBUG, 'Normal subtitle preferences skipped: the regex subtitle filter already matched')
        elif not settings.sub_prefs_on:
            log(LOG_DEBUG, 'Normal subtitle preferences disabled (sub_prefs_on=False), will try conditional subtitles')

        # Conditional subtitle preferences — runs if:
        # - condsub_prefs_on is enabled AND
        # - the regex subtitle filter did not select a subtitle (now or on the initial run).
        # It is deliberately NOT limited to the initial run: it is re-evaluated whenever the audio track
        # changes (onAVChange), exactly as in 1.0.8. (2.0 wrongly added an initial-run-only guard here.)
        if settings.condsub_prefs_on and not regex_sub_matched and not self.regex_sub_selected and not protect_sub:
            if settings.custom_condsub_prefs_on:
                trackIndex = self.evalCondSubPrefs(settings.custom_condsub)
            else:
                trackIndex = self.evalCondSubPrefs(settings.CondSubtitlePrefs)

            if trackIndex is None:
                log(LOG_DEBUG, 'Playback stopped during the conditional subtitle evaluation')
                return
            if trackIndex == -1:
                cond_decided_no_subs = True
                log(LOG_INFO, 'Conditional subtitle: disabling subs')
                self._show_subs(False)
            elif trackIndex == -2:
                log(LOG_INFO, 'Conditional subtitle: No matching preferences found for current audio stream.')
                if settings.turn_subs_off:
                    log(LOG_INFO, 'Conditional subtitle: Disabling subs.')
                    self._show_subs(False)
                else:
                    log(LOG_INFO, 'Conditional subtitle: Doing nothing.')
            elif trackIndex >= 0:
                self.setSubtitleStream(trackIndex)
                sub_preference_matched = True
                # Enable subtitles on match IF turn_subs_on is enabled OR if already enabled
                if settings.turn_subs_on or self.selected_sub_enabled:
                    if not self.selected_sub_enabled:
                        log(LOG_INFO, 'Conditional subtitle: enabling subs (preference match, turn_subs_on={0})'.format(settings.turn_subs_on))
                        self._show_subs(True)

        # Filename subtitle tag - lowest priority: only if regex, normal and conditional preferences did nothing
        if filename_sub >= 0 and filename_sub < len(self.subtitles) and not protect_sub:
            if regex_sub_matched:
                log(LOG_INFO, 'Filename preference: subtitle track {0} ignored - the regex subtitle filter matched and has priority'.format(filename_sub))
            elif sub_preference_matched or cond_decided_no_subs:
                log(LOG_INFO, 'Filename preference: subtitle track {0} ignored - a subtitle preference was applied and has priority'.format(filename_sub))
            else:
                log(LOG_INFO, 'Filename preference: Match, selecting subtitle track {0}'.format(filename_sub))
                self.setSubtitleStream(filename_sub)
                sub_preference_matched = True
                if settings.turn_subs_on:
                    log(LOG_DEBUG, 'Subtitle: enabling subs')
                    self._show_subs(True)

        # Final fallback (initial run only): regex / conditional / normal preferences selected nothing.
        # Use the subtitle flagged as default, else the first valid one. Only active together with the regex
        # filter or the conditional subtitles, so plain 1.0.x setups behave exactly as before.
        if (not self.LPM_initial_run_done
                and (settings.regex_sub_filter_enabled or settings.condsub_prefs_on)
                and not sub_preference_matched and not cond_decided_no_subs and not protect_sub):
            fallback_index = self.evalFallbackSubPrefs()
            if fallback_index >= 0:
                log(LOG_INFO, 'Subtitle fallback: no preference matched - selecting default/first valid subtitle track {0}'.format(
                    fallback_index))
                self.setSubtitleStream(fallback_index)
                sub_preference_matched = True
                if settings.turn_subs_on:
                    self._show_subs(True)
                elif settings.turn_subs_off:
                    self._show_subs(False)
            else:
                log(LOG_INFO, 'Subtitle fallback: no valid subtitle track available')

        if fast_subs:
            self.fast_subs_workaround()

        self.start_sub_converter()

    def fast_subs_workaround(self, initial_run=None):
        # Workaround to an old Kodi bug creating 10-15 sec latency when activating a subtitle track.
        # Force a short rewind to avoid 10-15sec delay and first few subtitles lines potentially lost
        #       but if we are very close to beginning, then restart from time 0
        #  Ignore this workaround if fast_subs_display option is disabled (default = 0) or no subs to be displayed
        # initial_run: part of the start of the playback (default: before the initial run is done)
        if initial_run is None:
            initial_run = not self.LPM_initial_run_done
        try:
            current_time = self.getTime()
        except RuntimeError:
            log(LOG_DEBUG, 'Fast Subs Display: playback stopped')
            return
        if (not self.selected_sub_enabled):
            # (1.0.9) Only perform seek back if a subtitle is active
            log(LOG_DEBUG, 'No subtitles activated - no need for workaround seekback.')
        elif (settings.fast_subs_display == 0):
            # Default is no seek back, which sometimes generate restart or freeze on slower systems
            log(LOG_DEBUG, 'Fast Subs Display disabled - Subs display will be slightly delayed 8-10sec.')
        elif (current_time <= 10 and settings.fast_subs_display >= 1):
            # This is an initial start, seek back to 0 is securing subs are displayed immediately
            log(LOG_DEBUG, 'Fast Subs Display on Start - Position time is {0} sec. Restart from 0.'.format(current_time))
            self.seekTime(0)
        elif (initial_run and settings.fast_subs_display == 2):
            # This is a resume, seek back 10sec to secure the 8sec normal Aud/Vid buffers are flushed
            log(LOG_DEBUG, 'Fast Subs Display on Resume - Position time is {0} sec. Resume with 10 sec rewind.'.format(current_time))
            self.seekTime(current_time - 10)
        else:
            # Audio Track change on-the-fly or a Resume with fast_sub_display on 'Start Only': no seek back at all.
            log(LOG_DEBUG, 'Position time was {0} sec. Subs display slightly delayed.'.format(current_time))

    def evalFallbackSubPrefs(self):
        """
        Last resort when nothing else selected a subtitle: the track flagged as default, otherwise the first
        valid track. Valid = not blacklisted, and not a Signs&Songs track while that toggle is on.
        :return: subtitle index, or -2 if there is no valid subtitle track
        """
        valid = []
        for sub in self.subtitles:
            sub_name = sub.get('name', '') or ''
            if self.isInBlacklist(sub_name, 'Subtitle'):
                continue
            if settings.ignore_signs_on and self.isSignsSub(sub_name):
                continue
            valid.append(sub)
        for sub in valid:
            if sub.get('isdefault', False):
                return sub['index']
        if valid:
            return valid[0]['index']
        return -2

    def getSelectedAudioLanguage(self):
        if self.selected_audio_stream and 'language' in self.selected_audio_stream:
            return self.selected_audio_stream['language']

        return ""

    def getSelectedAudioIndex(self):
        if self.selected_audio_stream and 'index' in self.selected_audio_stream:
            return self.selected_audio_stream['index']

        return -1

    def getSelectedSubtitleLanguage(self):
        if self.selected_sub and 'language' in self.selected_sub:
            return self.selected_sub['language']

        return ""

    def getSelectedSubtitleIndex(self):
        if self.selected_sub and 'index' in self.selected_sub:
            return self.selected_sub['index']

        return -1

    def start_sub_converter(self):
        """Sub converter: with Japanese, Korean or Chinese audio and an ASS/SSA subtitle selected (the video may
        have other subtitle formats as well), that subtitle is copied to a plain yellow SRT (subconvert.py): lines
        the ASS file does not position go to the top, positioned ones keep their place. The copy is selected.
        Runs in a thread: the file is read through for the track's events."""
        if (not settings.sub_converter_on or self.sub_converting
                or not (settings.regex_sub_filter_enabled or settings.condsub_prefs_on)):
            return
        self.sub_converting = True
        threading.Thread(target=self._sub_converter_run, daemon=True).start()

    def _converted_name(self, stream):
        return re.search(r'\[[0-9a-f]{6}-\d+\]', stream.get('name', '') or '') is not None

    def _sub_converter_job(self):
        """(video path, ordinal of the selected subtitle among the video's embedded subtitles, language) when the
        selected subtitle is to be converted, else None."""
        xbmc.sleep(500)                                  # Kodi applies LPM's switch
        if not self.getDetails() or not self.selected_sub_enabled or not self.selected_sub:
            return None
        audio = self.selected_audio_stream or {}
        if not any(langutils.stream_matches_language(c, audio, 'Audio') for c in ('jpn', 'kor', 'chi')):
            return None
        label = xbmc.getLocalizedString(21602)
        subs = [s for s in (self.subtitles or []) if not self._converted_name(s)]
        embedded = sorted((s for s in subs if langutils.external_name(s, label) is None), key=lambda s: s['index'])
        indexes = [s['index'] for s in embedded]
        selected = self.selected_sub.get('index')
        if selected not in indexes:
            return None                                  # an external (or an already converted) subtitle
        # the video may have any other subtitle formats too (SRT, PGS, SUP ...): only the selected track counts (any text format but SRT)
        codecs = self.embedded_subtitle_codecs()
        if codecs is None or len(codecs) != len(embedded):
            log(LOG_INFO, 'Sub converter: the subtitle formats of {0} cannot be read (only local or network Matroska '
                          '.mkv files can; {1} embedded streams, {2} tracks read)'.format(
                              subconvert.plain_location(self.getPlayingFile()), len(embedded),
                              None if codecs is None else len(codecs)))
            return None
        position = indexes.index(selected)
        if not subcodec.is_convertible(codecs[position]):
            log(LOG_INFO if subcodec.is_bitmap(codecs[position]) else LOG_DEBUG,
                'Sub converter: the selected subtitle is {0}: {1}'.format(
                    codecs[position], 'a picture format, it cannot be turned into text without OCR'
                    if subcodec.is_bitmap(codecs[position]) else 'nothing to convert'))
            return None
        return self.getPlayingFile(), position, self.selected_sub.get('language') or 'und', selected, codecs[position]

    def _picture_view(self):
        """Where the picture is on the screen (subconvert.video_view), None when Kodi does not tell."""
        try:
            number = lambda label: float(xbmc.getInfoLabel(label).replace(',', '') or 0)
            aspect = float(xbmc.getInfoLabel('VideoPlayer.VideoAspect').replace(',', '.') or 0)
            return subconvert.video_view(number('System.ScreenWidth'), number('System.ScreenHeight'), aspect)
        except ValueError:
            return None

    def _sub_converter_run(self):
        try:
            job = self._sub_converter_job()
            if not job:
                return
            video, ordinal, language, chosen, codec = job
            log(LOG_INFO, 'Sub converter: converting subtitle track {0} of {1} (the whole file is read: the first '
                          'time this can take a minute or more)'.format(ordinal + 1, subconvert.plain_location(video)))
            playing = lambda: self.isPlayingVideo() and self.getPlayingFile() == video
            as_ass = subcodec.is_ass(codec)                  # ASS/SSA stays ASS (styles, fonts, places), the rest becomes SRT
            view = None if as_ass else self._picture_view()
            destination = subconvert.target_path(__user_data_path__, video, ordinal, language, view,
                                                 'ass' if as_ass else 'srt')
            started = time.time()
            cues = subconvert.convert(video, ordinal, destination, lambda: not playing(),
                                      lambda msg: log(LOG_INFO, msg), view)
            if cues == 0:
                log(LOG_INFO, 'Sub converter: nothing converted for subtitle track {0}'.format(ordinal + 1))
                return
            log(LOG_INFO, 'Sub converter: subtitle track {0} converted ({1}) in {2:.1f} s: {3}'.format(
                ordinal + 1, 'reused' if cues < 0 else '{0} lines'.format(cues), time.time() - started,
                os.path.basename(destination)))
            if not playing():
                return
            if not self.getDetails() or (self.selected_sub or {}).get('index') != chosen:
                log(LOG_INFO, 'Sub converter: the subtitle was changed while converting - the copy is not selected')
                return
            self.sub_convert_quiet_until = time.time() + 5
            self.setSubtitles(destination)
            xbmc.sleep(1000)
            self.showSubtitles(True)
            self.refresh_subtitle_baseline()
            self.sub_convert_quiet_until = time.time() + 3
        except Exception as e:                           # never let the converter disturb the playback
            log(LOG_ERROR, 'Sub converter failed: {0}'.format(e))
        finally:
            self.sub_converting = False

    def regex_whole_word_hit(self, name):
        """True when the subtitle regex matches a whole word of the title ('Signs' in 'Signs and Song Subtitles'),
        not just a piece of a longer word ('titles' in 'Subtitles'): such a hit is not a false positive, the
        exclusion pattern does not apply to it."""
        for m in settings.regex_sub_filter.finditer(name):
            start, end = m.span()
            if end > start and not (start > 0 and name[start - 1].isalnum()) \
                    and not (end < len(name) and name[end].isalnum()):
                return True
        return False

    def embedded_subtitle_codecs(self):
        """CodecIDs of the embedded subtitle tracks of the playing file in Kodi's order, read once per video
        (Matroska only, None when unknown)."""
        try:
            playing = self.getPlayingFile()
        except RuntimeError:
            return None
        if self.sub_codecs[0] != playing:
            self.sub_codecs = (playing, subcodec.subtitle_codecs(playing) if playing else None)
            log(LOG_DEBUG, 'Embedded subtitle codecs: {0}'.format(self.sub_codecs[1]))
        return self.sub_codecs[1]

    def ass_subtitle_indexes(self, subs):
        """Indexes of the subtitle streams in subs that are ASS/SSA tracks. Kodi lists the embedded subtitles
        first, in file order, then the external ones: the file's track list is only used when it has as many
        subtitle tracks as Kodi shows embedded ones, an external file counts as ASS by its name (.ass / .ssa)."""
        label = xbmc.getLocalizedString(21602)
        embedded = [s for s in subs if langutils.external_name(s, label) is None]
        codecs = self.embedded_subtitle_codecs() if embedded else None
        ass = set()
        if codecs is not None and len(codecs) == len(embedded):
            for s, codec in zip(sorted(embedded, key=lambda s: s['index']), codecs):
                if subcodec.is_ass(codec):
                    ass.add(s['index'])
        elif embedded:
            log(LOG_DEBUG, 'Subtitle formats unknown ({0} embedded streams, {1} tracks read): the ASS preference '
                           'is skipped'.format(len(embedded), None if codecs is None else len(codecs)))
        for s in subs:
            if langutils.external_name(s, label) is not None and re.search(r'\.(?:ass|ssa)\b', s.get('name', ''), re.I):
                ass.add(s['index'])
        return ass

    def evalRegexSubPrefs(self):
        """
        Evaluate regex subtitle preferences:
        1. every subtitle (in track order) whose title matches the pattern is a candidate
        2. the exclusion pattern (if on) removes a candidate, unless the pattern matched a whole word of its
           title ('Signs and Song Subtitles' stays: 'Signs' is a word, the exclusion is for 'Subtitles' only
           matching a piece of a word)
        3. of the candidates the first ASS/SSA track is taken (the better format for signs & songs), else the
           first one

        Returns the subtitle track index if a candidate is left, -2 if no match.
        """
        log(LOG_DEBUG, 'Evaluating regex subtitle preferences')
        if not settings.regex_sub_filter_enabled or settings.regex_sub_filter is None:
            return -2

        candidates = []
        for sub in sorted(self.subtitles, key=lambda s: s.get('index', 0)):
            sub_name = sub.get('name', '') or ''
            try:
                if not settings.regex_sub_filter.search(sub_name):
                    continue
                if settings.regex_sub_exclusion and settings.regex_sub_exclusion.search(sub_name):
                    if not self.regex_whole_word_hit(sub_name):
                        log(LOG_DEBUG, 'Regex subtitle: Excluded via exclusion pattern: {0}'.format(sub_name))
                        continue
                    log(LOG_DEBUG, 'Regex subtitle: {0} matches the exclusion pattern, but the regex matched a whole '
                                   'word - kept'.format(sub_name))
                candidates.append(sub)
            except Exception as e:
                log(LOG_ERROR, 'Regex search error on subtitle "{0}": {1}'.format(sub_name, str(e)))

        if not candidates:
            log(LOG_INFO, 'Regex subtitle preference: No matching subtitle track found')
            return -2

        chosen = candidates[0]
        if len(candidates) > 1:
            ass = self.ass_subtitle_indexes(self.subtitles) & set(s['index'] for s in candidates)
            chosen = next((s for s in candidates if s['index'] in ass), candidates[0])
            log(LOG_INFO, 'Regex subtitle preference: {0} matching tracks {1}{2}'.format(
                len(candidates), [s['index'] for s in candidates],
                ', ASS tracks {0}'.format(sorted(ass)) if ass else ''))
        log(LOG_INFO, 'Regex subtitle preference: Match found - selecting subtitle track {0} ({1})'.format(
            chosen['index'], chosen.get('name', '')))
        return chosen['index']

    def evalFilenamePrefs(self):
        log(LOG_DEBUG, 'Evaluating filename preferences')
        audio = -1
        sub = -1
        filename = self.getPlayingFile()
        matches = settings.reg.findall(filename)
        fileprefs = []
        for m in matches:
            sp = settings.split.split(m)
            fileprefs.append(sp)

        for pref in fileprefs:
            if len(pref) == 2:
                if (pref[0].lower() == 'audiostream'):
                    audio = int(pref[1])
                    log(LOG_INFO, 'audio track extracted from filename: {0}'.format(audio))
                elif (pref[0].lower() == 'subtitle'):
                    sub = int(pref[1])
                    log(LOG_INFO, 'subtitle track extracted from filename: {0}'.format(sub))
        log(LOG_DEBUG, 'filename: audio: {0}, sub: {1} ({2})'.format(audio, sub, filename))
        return audio, sub

    def evalAudioPrefs(self, audio_prefs):
        log(LOG_DEBUG, 'Evaluating audio preferences')
        log(LOG_DEBUG, 'Audio names containing the following keywords are blacklisted: {0}'.format(
            ','.join(settings.audio_keyword_blacklist)))
        
        log(LOG_DEBUG, 'Original Audio tracks to be preferred if present: {0}'.format(
            ','.join(settings.audio_original_preflist)))
        
        if settings.audio_original_preflist_enabled and settings.audio_original_preflist:
            AudioOriginalTrackIndex = self.get_original_audio_track_index()
            # Audio Original tracks are preferred. If one is found we choose it and skip remaining preference evaluation.
            if AudioOriginalTrackIndex is not None:
                return AudioOriginalTrackIndex
            
        i = 0
        for pref in audio_prefs:
            i += 1
            g_t, preferences = pref
            # genre or tags are given (g_t not empty) but none of them matches the video's tags/genres
            if g_t and (not (self.genres_and_tags & g_t)):
                continue

            if g_t:
                log(LOG_INFO, 'Audio: genre/tag preference {0} met with intersection {1}'.format(g_t, (
                            self.genres_and_tags & g_t)))
            for pref in preferences:
                name, codes = pref
                codes = codes.split(r',')
                for code in codes:
                    if (code is None):
                        log(LOG_DEBUG, 'continue')
                        continue

                    def accept(stream):
                        # filter out audio tracks matching Keyword Blacklist
                        if self.isInBlacklist(stream.get('name', '') or '', 'Audio'):
                            log(LOG_INFO,
                                'Audio: one audio track is found matching Keyword Blacklist : {0}. Skipping it.'.format(
                                    ','.join(settings.audio_keyword_blacklist)))
                            return False
                        return True

                    # the tracks that fit best: a regional preference (en-AU) prefers its region
                    found = self.best_matches(code, name, self.audiostreams, 'Audio', accept)
                    if found and self.getSelectedAudioIndex() in found:
                        log(LOG_INFO, 'Selected audio language matches preference {0} ({1})'.format(i, name))
                        return -1
                    if found:
                        log(LOG_INFO, 'Language of Audio track {0} matches preference {1} ({2})'.format(
                            (found[0] + 1), i, name))
                        return found[0]
                    log(LOG_INFO, 'Audio: preference {0} ({1}:{2}) not available'.format(i, name, code))
                i += 1
        return -2

    def evalSubPrefs(self, sub_prefs):
        log(LOG_DEBUG, 'Evaluating subtitle preferences')
        log(LOG_DEBUG, 'Subtitle names containing the following keywords are blacklisted: {0}'.format(
            ','.join(settings.subtitle_keyword_blacklist)))
        i = 0
        for pref in sub_prefs:
            i += 1
            g_t, preferences = pref
            # genre or tags are given (g_t not empty) but none of them matches the video's tags/genres
            if g_t and (not (self.genres_and_tags & g_t)):
                continue

            if g_t:
                log(LOG_INFO, 'SubPrefs : genre/tag preference {0} met with intersection {1}'.format(g_t, (
                            self.genres_and_tags & g_t)))
            for pref in preferences:
                if len(pref) == 2:
                    name, codes = pref
                    forced = 'false'
                else:
                    name, codes, forced = pref
                codes = codes.split(r',')
                for code in codes:
                    if (code is None):
                        log(LOG_DEBUG, 'continue')
                        continue

                    # the subtitles that fit best: a regional preference (pt-BR) prefers its region
                    to_chose_subtitle_indexes = self.best_matches(code, name, self.subtitles, 'Subtitle',
                                                                  self.subtitle_filter(forced, 'SubPrefs'))

                    # If our current subtitle is eligible, we will not change it
                    if self.getSelectedSubtitleIndex() in to_chose_subtitle_indexes:
                        log(LOG_INFO, 'SubPrefs : Selected subtitle language matches preference {0} ({1})'.format(i, name))
                        return -1

                    if len(to_chose_subtitle_indexes) > 0:
                        # if we have more than one subtitles, we will take the first one
                        to_chose_subtitle_index = to_chose_subtitle_indexes[0]
                        log(LOG_INFO, 'SubPrefs : Found {0} matching subtitles, using first at index {1}'.format(
                            len(to_chose_subtitle_indexes), to_chose_subtitle_index))
                        return to_chose_subtitle_index

                    log(LOG_INFO, 'SubPrefs : preference {0} ({1}:{2}) not available'.format(i, name, code))
                i += 1
        return -2

    def evalCondSubPrefs(self, condsub_prefs):
        log(LOG_DEBUG, 'Evaluating conditional subtitle preferences')
        log(LOG_DEBUG, 'Subtitle names containing the following keywords are blacklisted: {0}'.format(
            ','.join(settings.subtitle_keyword_blacklist)))
        # if the audio track has been changed wait some time
        if (self.audio_changed and settings.delay > 0):
            log(LOG_DEBUG, "Delaying preferences evaluation by {0} ms".format(4 * settings.delay))
            xbmc.sleep(4 * settings.delay)
        log(LOG_DEBUG, 'Getting video properties')
        if not self.getDetails():
            return None                       # playback stopped: evalPrefs ends here
        i = 0
        for pref in condsub_prefs:
            i += 1
            g_t, preferences = pref
            # genre or tags are given (g_t not empty) but none of them matches the video's tags/genres
            if g_t and (not (self.genres_and_tags & g_t)):
                continue

            if g_t:
                log(LOG_INFO, 'CondSubs : genre/tag preference {0} met with intersection {1}'.format(g_t, (
                            self.genres_and_tags & g_t)))
            for pref in preferences:
                audio_name, audio_codes, sub_name, sub_codes, forced, ss_tag = pref
                # manage multiple audio and/or subtitle 3-letters codes if present (ex. German = ger,deu)
                audio_codes = audio_codes.split(r',')
                sub_codes = sub_codes.split(r',')
                nbr_sub_codes = len(sub_codes)

                for audio_code in audio_codes:
                    if audio_code is None:
                        log(LOG_DEBUG, 'continue')
                        continue

                    if (self.selected_audio_stream and
                            'language' in self.selected_audio_stream and
                            (self.stream_matches_language(audio_code, self.selected_audio_stream, 'Audio') or
                             audio_name ==
                             self.selected_audio_stream['language'])):
                        log(LOG_INFO,
                            'CondSubs : Selected audio language matches conditional preference {0} ({1}:{2}), force tag is {3}'.format(
                                i, audio_name, sub_name, forced))
                        for sub_code in sub_codes:
                            if sub_code == "non":
                                if forced == 'true':
                                    log(LOG_INFO,
                                        'CondSubs : Subtitle condition is None but forced is true, searching a forced subtitle matching selected audio...')

                                    found = self.best_matches(audio_code, audio_name, self.subtitles, 'Subtitle',
                                                              self.subtitle_filter(forced, 'CondSubs'))
                                    if found:
                                        log(LOG_INFO,
                                            'CondSubs : Language of subtitle {0} matches audio preference {1} ({2}:{3}) with forced overriding rule {4}'.format(
                                                (found[0] + 1), i, audio_name, sub_name, forced))
                                        return found[0]
                                    log(LOG_INFO,
                                        'CondSubs : no match found for preference {0} ({1}:{2}) with forced overriding rule {3}'.format(
                                            i, audio_name, sub_name, forced))
                                return -1
                            else:
                                # the subtitles that fit best: a regional preference (pt-BR) prefers its region
                                to_chose_subtitle_indexes = self.best_matches(
                                    sub_code, sub_name, self.subtitles, 'Subtitle',
                                    self.subtitle_filter(forced, 'CondSubs', signs_only=(ss_tag == 'true')))
                                if to_chose_subtitle_indexes:
                                    log(LOG_INFO,
                                        'CondSubs : subtitles {0} match conditional preference {1} ({2}:{3}) forced {4} & ss-tag {5}'.format(
                                            [x + 1 for x in to_chose_subtitle_indexes], i, audio_name, sub_name, forced, ss_tag))

                                current_subtitle_index = self.getSelectedSubtitleIndex()

                                # If our current subtitle is eligible for the condition, we will not change it
                                if current_subtitle_index in to_chose_subtitle_indexes:
                                    log(LOG_INFO,
                                        'CondSubs : already selected subtitle matches preference {0} ({1}:{2}) with forced {3} & ss-tag {4}'.format(
                                            i, audio_name, sub_name, forced, ss_tag))
                                    return current_subtitle_index

                                if len(to_chose_subtitle_indexes) > 0:
                                    # if we have more than one subtitles, we will take the first one
                                    to_chose_subtitle_index = to_chose_subtitle_indexes[0]
                                    log(LOG_INFO,
                                        'CondSubs : Found {0} matching subtitles, using first at index {1}'.format(
                                        len(to_chose_subtitle_indexes), to_chose_subtitle_index))

                                    return to_chose_subtitle_index

                                nbr_sub_codes -= 1
                                if nbr_sub_codes == 0:
                                    log(LOG_INFO,
                                        'CondSubs : no match found for preference {0} ({1}:{2}) with forced {3} & ss-tag {4}'.format(
                                            i, audio_name, sub_name, forced, ss_tag))
                i += 1
        return -2

    def get_original_audio_track_index(self):
        """
        Get the audio track index that matches the original preferred list. If no audio track matches, return None.
        The audio track is searched by language, checking for the isoriginal tag. If multiple original found (weird...)
        the first one is returned. Blacklisted original audio tracks, if any, are excluded (1.0.9).
        The list may contain 2-letter, 3-letter (B/T) codes or 'any' (every original track qualifies).

        :return: The first audio track index tagged as isoriginal, matching the list and not blacklisted.
                -1 if the current selected audio track is already correct (to avoid unnecessary audio change)
                 None if no original audio track found or no match.
        """
        found = []
        for stream in self.audiostreams:
            if 'index' not in stream or not stream.get('isoriginal', False):
                continue
            if self.isInBlacklist(stream.get('name', '') or '', 'Audio'):
                log(LOG_INFO, "Audio: one Original audio track matches Keyword Blacklist : {0}. Skipping it.".format(
                    ','.join(settings.audio_keyword_blacklist)))
                continue
            score = 1 if settings.audio_original_any else max(
                [langutils.match_score(code, stream, 'Audio') for code in settings.audio_original_langs] or [0])
            if score:
                found.append((score, stream))
        # a regional entry (en-AU) prefers a track of its region
        best = max([score for score, stream in found] or [0])
        found = [stream for score, stream in found if score == best]

        preflist = ",".join(settings.audio_original_preflist)
        if found:
            first = found[0]
            if first['index'] != self.getSelectedAudioIndex():
                log(LOG_INFO, "Audio: Found at least one preferred original audio track among " + preflist +
                    " . Picking first: " + str(first.get('language', '')))
                return first['index']
            # Found audio track is already the selected one - No need to change
            log(LOG_INFO, "Audio: Selected audio track matches preferred original list " + preflist +
                " . Keeping it   : " + str(first.get('language', '')))
            return -1
        log(LOG_INFO, "Audio: No preferred original audio track found among " + preflist +
            " . Continue preferences evaluation...")
        return None

    def isInBlacklist(self, TrackName, TrackType):
        found = False
        test = TrackName.lower()
        if (TrackType == 'Subtitle' and settings.subtitle_keyword_blacklist_enabled and any(
                keyword in test for keyword in settings.subtitle_keyword_blacklist)):
            found = True
        elif (TrackType == 'Audio' and settings.audio_keyword_blacklist_enabled and any(
                keyword in test for keyword in settings.audio_keyword_blacklist)):
            found = True
        return found

    def isSignsSub(self, subName):
        test = subName.lower()
        matches = ['signs']
        return any(x in test for x in matches)

    def testForcedFlag(self, forced, subName, subForcedTag):
        test = subName.lower()
        matches = ['forced', 'forcés']
        found = any(x in test for x in matches)
        # Only when looking for forced subs :
        #   in case the sub name is plain empty or not well documented, 
        #   check also the sub isforced tag and consider it a match if set
        if (forced and not found and subForcedTag):
            found = True
        return ((forced == 'false') and not found) or ((forced == 'true') and found)

    def isExternalSub(self, subName):
        test = subName.lower()
        matches = ['ext']
        return any(x in test for x in matches)

    def subtitle_file_tags(self, externals):
        """Language tags of the subtitle files of the playing video (its folder, a Subs / Subtitles subfolder and
        Kodi's custom subtitle folder), read once per video and again when Kodi's number of external subtitles
        changes (one downloaded during playback). [] for streams without a folder (plugin, http ...)."""
        try:
            playing = self.getPlayingFile()
        except RuntimeError:
            return []
        if self.external_sub_files[0] == (playing, externals):
            return self.external_sub_files[1]
        tags = []
        scheme = re.match(r'^([a-z0-9]+)://', playing or '', re.IGNORECASE)
        if playing and (not scheme or scheme.group(1).lower() in ('smb', 'nfs', 'ftp', 'sftp', 'dav', 'davs')):
            folder, video_name = os.path.split(playing)
            try:
                dirs, files = xbmcvfs.listdir(folder + '/')
            except Exception as e:
                # cached like a result: listed again only when Kodi's number of external subtitles changes
                log(LOG_INFO, 'External subtitles: cannot list the folder of {0}: {1}'.format(playing, e))
                self.external_sub_files = ((playing, externals), [])
                return []
            sep = '/' if scheme or '/' in folder else os.sep
            # the subfolders Kodi searches for subtitles
            others = [folder + sep + d for d in dirs
                      if d.lower() in ('subs', 'subtitles', 'sub', 'subtitle', 'vobsubs', 'vobsub')]
            try:
                custom = simplejson.loads(xbmc.executeJSONRPC(simplejson.dumps(
                    {"jsonrpc": "2.0", "method": "Settings.GetSettingValue",
                     "params": {"setting": "subtitles.custompath"}, "id": 1}))).get('result', {}).get('value')
            except Exception:
                custom = None
            if custom:
                others.append(custom.rstrip('/\\'))
            for other in others:
                try:
                    files += xbmcvfs.listdir(other + '/')[1]
                except Exception as e:     # an offline share: its files are missed, the rest is used and kept
                    log(LOG_INFO, 'External subtitles: cannot list {0}: {1}'.format(other, e))
            for name in files:
                tag = langutils.subtitle_file_tag(video_name, name)
                if tag:
                    tags.append(tag)
            log(LOG_DEBUG, 'External subtitle files: {0}'.format([t['tag'] for t in tags]))
        self.external_sub_files = ((playing, externals), tags)
        return tags

    def repair_external_subtitles(self):
        """Kodi misreads external subtitle file names with a region (Movie.pt-BR.srt -> language 'br'):
        put the language the file name says into the stream dicts. The subtitle files of the video are matched
        onto Kodi's external streams (langutils.match_external_files); where that finds nothing, the stream's
        name and reported language are read (langutils.repair_external)."""
        label = xbmc.getLocalizedString(21602)    # "(External)" in the GUI language
        subs = list(self.subtitles or [])
        externals = sum(1 for sub in subs if langutils.external_name(sub, label) is not None)
        if not externals:
            return
        # the result depends only on Kodi's stream list (and the files, read once): worked out once per list
        key = tuple((sub.get('index'), sub.get('name'), sub.get('language')) for sub in subs)
        if self.external_sub_tags[0] == key:
            tags = self.external_sub_tags[1]
        else:
            from_files = langutils.match_external_files(subs, self.subtitle_file_tags(externals), label)
            tags = {}
            for sub in subs:
                tag = from_files.get(sub['index']) or langutils.repair_external(sub, label)
                if tag:
                    tags[sub['index']] = tag
            self.external_sub_tags = (key, tags)
        for sub in subs + ([self.selected_sub] if self.selected_sub else []):
            tag = tags.get(sub.get('index'))
            if not tag or tag == sub.get('language'):
                continue
            if sub is not self.selected_sub:
                log(LOG_DEBUG, 'External subtitle {0!r}: language {1!r} read as {2!r}'.format(
                    sub.get('name'), sub.get('language'), tag))
            sub['language'] = tag

    def getDetails(self):
        """Read the player's streams into the cache. :return: False when playback stopped meanwhile (the cache
        is then left as it was), True otherwise"""
        activePlayers = '{"jsonrpc": "2.0", "method": "Player.GetActivePlayers", "id": 1}'
        json_query = xbmc.executeJSONRPC(activePlayers)
        # json_query = unicode(json_query, 'utf-8', errors='ignore')
        json_response = simplejson.loads(json_query)
        players = json_response.get('result') or []
        if not players:
            # playback stopped meanwhile (Kodi fires onAVChange while stopping): keep the cached details
            log(LOG_DEBUG, 'getDetails: no active player')
            return False
        activePlayerID = next((p['playerid'] for p in players if p.get('type') == 'video'), players[0]['playerid'])
        details_query_dict = {"jsonrpc": "2.0",
                              "method": "Player.GetProperties",
                              "params": {"properties":
                                             ["currentaudiostream", "audiostreams", "subtitleenabled",
                                              "currentsubtitle", "subtitles"],
                                         "playerid": activePlayerID},
                              "id": 1}
        details_query_string = simplejson.dumps(details_query_dict)
        json_query = xbmc.executeJSONRPC(details_query_string)
        # json_query = unicode(json_query, 'utf-8', errors='ignore')
        json_response = simplejson.loads(json_query)

        if 'result' in json_response and json_response['result'] != None:
            self.selected_audio_stream = json_response['result']['currentaudiostream']
            self.selected_sub = json_response['result']['currentsubtitle']
            self.selected_sub_enabled = json_response['result']['subtitleenabled']
            self.audiostreams = json_response['result']['audiostreams']
            self.subtitles = json_response['result']['subtitles']
            self.repair_external_subtitles()
        else:
            # the player stopped between the two queries: keep the cached details
            log(LOG_DEBUG, 'getDetails: no player properties ({0})'.format(json_response.get('error')))
            return False
        log(LOG_DEBUG, json_response)

        if (
                not settings.custom_condsub_prefs_on and not settings.custom_audio_prefs_on and not settings.custom_sub_prefs_on):
            log(LOG_DEBUG, 'No custom prefs used at all, skipping extra Video tags/genres JSON query.')
            self.genres_and_tags = set()
            return True

        genre_tags_query_dict = {"jsonrpc": "2.0",
                                 "method": "Player.GetItem",
                                 "params": {"properties":
                                                ["genre", "tag"],
                                            "playerid": activePlayerID},
                                 "id": 1}
        genre_tags_query_string = simplejson.dumps(genre_tags_query_dict)
        json_query = xbmc.executeJSONRPC(genre_tags_query_string)
        # json_query = unicode(json_query, 'utf-8', errors='ignore')
        json_response = simplejson.loads(json_query)
        if 'result' in json_response and json_response['result'] != None:
            gt = []
            if 'genre' in json_response['result']['item']:
                gt = json_response['result']['item']['genre']
            if 'tag' in json_response['result']['item']:
                gt.extend(json_response['result']['item']['tag'])
            self.genres_and_tags = set(map(lambda x: x.lower(), gt))
        else:
            self.genres_and_tags = set()          # the player stopped meanwhile: no genres / tags
        log(LOG_DEBUG, 'Video tags/genres: {0}'.format(self.genres_and_tags))
        log(LOG_DEBUG, json_response)
        return True

    def __del__(self):
        """ Ensure that the watcher thread is properly stopped when the object is deleted """
        if hasattr(self, 'lang_pref_watcher'):
            self.lang_pref_watcher.stop()
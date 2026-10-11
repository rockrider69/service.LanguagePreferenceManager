import re
import xbmc, xbmcaddon
import langutils
from logger import log, LOG_NONE, LOG_INFO, LOG_DEBUG, LOG_ERROR


class PrefParser:
    
    def __init__( self ):
        addon = xbmcaddon.Addon()
        self.logLevel = addon.getSetting('log_level')
        if self.logLevel and len(self.logLevel) > 0:
            self.logLevel = int(self.logLevel)
        else:
            self.logLevel = LOG_INFO
        self.custom_prefs_delim = r'>'
        self.custom_genre_prefs_delim = r'|'
        self.custom_g_t_pref_delim = r'#'
        self.custom_g_t_delim = r','
        self.custom_condSub_delim = r':'
    
    def parsePrefString(self, pref_string):
        preferences = []
        if not pref_string:
            return preferences
        
        if (pref_string.find(self.custom_genre_prefs_delim) > 0):
            c_prefs = pref_string.split(self.custom_genre_prefs_delim)
        else:
            c_prefs = [pref_string]
            
        for s_pref in c_prefs:
            pref = self.parseSinglePref(s_pref)
            if (pref):
                preferences.append(pref)
                
        if (len(preferences) == 1
            and isinstance(preferences[0], list)):
            preferences = preferences[0]

        return preferences
    
    def parseSinglePref(self, s_pref):
        if (s_pref.find(self.custom_g_t_pref_delim) > 0):
            g_pref = s_pref.split(self.custom_g_t_pref_delim)
            if len(g_pref ) != 2:
                log(LOG_INFO, 'Parse error: {0}'.format(g_pref))
                return []
            else:
                return (set(map(lambda x:x.lower(), g_pref[0].split(self.custom_g_t_delim))),
                        self.parsePref(g_pref[1]))
        else:
            return (set(), self.parsePref(s_pref))
            
    def lang_pref(self, value):
        """Custom preference text -> (english name, canonical code), or (None, None) when empty.
        Accepts 2-letter (en), 3-letter B/T (eng, ger, deu), BCP47-ish (pt-BR, en-AU, zh-Hant) codes and the
        specials. A region or script is kept ('eng-AU'), see langutils.match_score()."""
        code = langutils.canonical_tag(value)
        if not code:
            return (None, None)
        base, region = langutils.parse_tag(code)
        if region and not langutils.valid_region(region):
            log(LOG_INFO, 'Custom prefs: {0} is not a region or script - using the language alone: {1}'.format(
                region, value))
            code = base
        if not langutils.is_known(code):
            log(LOG_INFO, 'Custom prefs: language code {0} is not in the Kodi language tables - using it as is'.format(value))
        return (langutils.display_name(code), code)

    @staticmethod
    def split_tags(text):
        """Remove the trailing option tags '-ff' (forced) and '-ss' (Signs & Songs), in any order and as exact
        suffixes (never character stripping), so that they are never read as a region (en-ff-ss).
        :return: (text, forced, signs)"""
        found = set()
        while text.lower().endswith(('-ff', '-ss')):
            found.add(text[-2:].lower())
            text = text[:-3]
        return text, 'ff' in found, 'ss' in found

    def parsePref(self, prefs):
        lang_prefs = []
        if (prefs.find(self.custom_prefs_delim) > 0):
            s_prefs = prefs.split(self.custom_prefs_delim)
        else:
            s_prefs = [prefs]
        for pref in s_prefs:
            # custom cond sub pref
            if (pref.find(self.custom_condSub_delim) > 0):
                pref = pref.split(self.custom_condSub_delim)
                if len(pref) != 2:
                    log(LOG_INFO, 'Custom cond subs prefs parse error: {0}'.format(pref))
                else:
                    audio_text = pref[0].strip()
                    sub_text = pref[1].strip()
                    # Sub tags like Eng:Jpn-ff to prioritize Forced tracks of another language, Eng:Eng-ss to
                    # prioritize Signs&Songs tracks
                    sub_text, ff_tag, ss_found = self.split_tags(sub_text)
                    ss_tag = 'true' if ss_found else 'false'
                    temp_a = self.lang_pref(audio_text)
                    temp_s = self.lang_pref(sub_text)
                    if (temp_a[0] and temp_a[1] and temp_s[0] and temp_s[1]):
                        if (temp_s[1] == langutils.NON or ff_tag):
                            forced_tag = 'true'
                        else:
                            forced_tag = 'false'
                        lang_prefs.append((temp_a[0], temp_a[1], temp_s[0], temp_s[1], forced_tag, ss_tag))
                    else:
                        log(LOG_INFO, 'Custom cond sub prefs: lang code not found! '
                                      'Please report this: {0}:{1}'.format(audio_text, sub_text))
            # custom audio or subtitle pref
            else:
                text, ff_tag, ss_found = self.split_tags(pref.strip())
                if ff_tag or ss_found:
                    log(LOG_INFO, 'Custom prefs: the -ff / -ss tags only apply to conditional subtitle rules, '
                                  'ignored in {0}'.format(pref))
                temp_pref = self.lang_pref(text)
                if temp_pref[0]:
                    lang_prefs.append(temp_pref)
                else:
                    log(LOG_INFO, 'Custom audio prefs: lang code {0} not found! '
                                  'Please report this'.format(pref))
        return lang_prefs

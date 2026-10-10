# -*- coding: utf-8 -*-
"""
Language code helpers for Language Preference Manager.

This is the ONE place that knows how to compare language codes. Everything else (settings spinners,
custom preference strings, the regex/conditional/normal subtitle logic, the Original audio list and the
stored per-media overrides) goes through normalize() / lang_matches() / stream_matches_language().

Accepted input forms
  * ISO 639-1  (2 letters)            en, ja, de        <- what Kodi 22 "Piers" reports for streams
  * ISO 639-2  (3 letters, /B and /T) eng, ger, deu, fre, fra ...
  * retired / non-standard 3 letters  scc, scr
  * BCP 47 style tags                 pt-BR, zh-Hans, en_US, es-419 (region or script kept, see below)
  * LPM special codes                 any, org, unk, und, non

Canonical form = ISO 639-2/B (3 letters, lower case) - the same code family Kodi itself uses internally.
normalize() always returns the base language ('pob' for Brazilian Portuguese, as before).

Regions and scripts (en-AU, es-419, zh-Hant, pt-BR ...)
  A preference may carry a region: canonical_tag() gives 'eng-AU', 'spa-419', 'chi-Hant' ('pob' for pt-BR).
  Kodi 22 drops the region of embedded tracks (an en-AU track is reported as 'en'), so the region of a stream
  is read from its language tag when it has one, else from its title ('English (Australia)', 'Brasileiro').
  match_score() rates a stream for a preference: 2 = language and region match, 1 = the language matches and
  at least one side has no region, 0 = no match (also: both have a region and they differ). The evaluators take
  the best score, so a regional preference prefers its region but still accepts a track of unknown region.
  A plain preference (en, Portuguese) scores 1 on every track of its language: the first one wins, as before.
"""
import re

from langcodes import (LANGUAGES, ISO639_1_TO_2B, ISO639_2T_TO_2B, LEGACY_TO_2B,
                       LANGUAGE_NAMES, NAME_TO_2B)

ANY, ORG, UNK, UND, NON = 'any', 'org', 'unk', 'und', 'non'
SPECIAL_CODES = frozenset((ANY, ORG, UNK, UND, NON))

_SPECIAL_ALIASES = {
    'any': ANY,
    'org': ORG, 'original': ORG,
    'unk': UNK, 'unknown': UNK,
    'und': UND, 'undefined': UND, 'undetermined': UND,
    'non': NON, 'none': NON,
}

BRAZILIAN_PORTUGUESE = 'pob'
_PT_BR_ALIASES = frozenset(('pob', 'pb', 'pt-br', 'ptbr'))
# common non-standard names of the two Chinese scripts (Movie.chs.srt, Movie.cht.srt)
_CHINESE_SCRIPT_ALIASES = {'chs': 'Hans', 'cht': 'Hant'}

# Codes that carry no usable language information: for those the track title is consulted instead.
_NO_LANGUAGE = frozenset(('', UND, UNK, 'mul', 'zxx', 'mis'))

_DEPRECATED_ALPHA2 = frozenset(('in', 'iw', 'ji', 'jw'))

_SPECIAL_NAMES = {ANY: 'Any', ORG: 'Original', UNK: 'Unknown', UND: 'Undefined', NON: 'None'}

# reverse tables, built once
_B_TO_A2 = {}
for _a2, _b in sorted(ISO639_1_TO_2B.items()):
    if _a2 not in _DEPRECATED_ALPHA2:
        _B_TO_A2.setdefault(_b, _a2)
_B_TO_T = {_b: _t for _t, _b in ISO639_2T_TO_2B.items()}
_SPINNER_NAMES = {}
for _row in LANGUAGES:
    _SPINNER_NAMES[_row[4]] = _row
_SPINNER_LANG_3 = frozenset(ISO639_1_TO_2B.values())   # languages that also have a 2-letter code

_WORD = re.compile(r"[a-z\u00c0-\u024f]+")

# region aliases per language: the countries of a group share one region code
_REGION_ALIASES = {
    'eng': {'UK': 'GB'},
    'spa': {c: '419' for c in ('MX', 'AR', 'CO', 'CL', 'PE', 'VE', 'UY', 'PY', 'BO', 'EC', 'GT', 'CR', 'PA', 'DO',
                                'HN', 'NI', 'SV', 'CU', 'PR', 'US', 'LA')},
    'chi': {'CN': 'Hans', 'SG': 'Hans', 'TW': 'Hant', 'HK': 'Hant', 'MO': 'Hant', 'CHS': 'Hans', 'CHT': 'Hant'},
}

# words in a track title that name a region or script (lower case; whole words)
_TITLE_REGIONS = (
    ('AU', ('australia', 'australian')),
    ('GB', ('uk', 'british', 'britain', 'gb', 'england')),
    ('US', ('us', 'usa', 'american')),
    ('BR', ('brazil', 'brazilian', 'brasil', 'brasileiro', 'brasileira', 'br', 'ptbr')),
    ('PT', ('portugal', 'european', 'europeu', 'europeu', 'pt')),
    ('419', ('latino', 'latam', 'latinoamerica', 'latinoamericano', 'latinoamérica', 'latinoamericano', '419',
             'mexico', 'méxico', 'mexican', 'mx')),
    ('ES', ('spain', 'castilian', 'castellano', 'españa', 'espana', 'european', 'es')),
    ('CA', ('canada', 'canadian', 'canadien', 'quebec', 'québec', 'québécois', 'quebecois', 'vfq', 'ca')),
    ('FR', ('france', 'vff', 'fr')),
    ('IN', ('india', 'indian')),
    ('CH', ('switzerland', 'swiss', 'schweiz', 'schweizer', 'suisse', 'svizzera')),
    ('AT', ('austria', 'austrian', 'österreich', 'osterreich', 'österreichisch')),
    ('BE', ('belgium', 'belgian', 'belgique', 'belge', 'belgië', 'belgie', 'vlaams', 'flemish')),
    ('Hans', ('simplified', 'chs', 'sc', 'hans', 'cn')),
    ('Hant', ('traditional', 'cht', 'tc', 'hant', 'tw', 'hk')),
)
# regions that only make sense for one language ('European' is Portuguese or Spanish, 'pt' only for Portuguese)
_REGION_LANGUAGES = {'BR': ('por',), 'PT': ('por',), '419': ('spa',), 'ES': ('spa',), 'Hans': ('chi',),
                     'Hant': ('chi',), 'CA': ('fre', 'eng'), 'FR': ('fre',), 'AU': ('eng',), 'GB': ('eng',),
                     'US': ('eng', 'spa')}
# short title words count only in upper case ("English (US)", not "us" in a sentence)
_TITLE_TOKEN = re.compile(r"[A-Za-z0-9À-ɏ]+")
_TITLE_TAG = re.compile(r"(?<![A-Za-z0-9])[A-Za-z]{2,3}[-_](?:[A-Za-z]{2}|[0-9]{3}|[A-Za-z]{4})(?![A-Za-z0-9])")
_LATIN_AMERICA = re.compile(r"\blatin[\s-]*americ", re.IGNORECASE)

_REGION_NAMES = {'AU': 'Australia', 'GB': 'UK', 'US': 'US', 'BR': 'Brazil', 'PT': 'Portugal', '419': 'Latin America',
                 'ES': 'Spain', 'CA': 'Canada', 'FR': 'France', 'Hans': 'Simplified', 'Hant': 'Traditional',
                 'IN': 'India', 'CH': 'Switzerland', 'AT': 'Austria', 'BE': 'Belgium'}


def normalize(code):
    """Return the canonical key for any accepted code form, or '' for empty/None.

    >>> normalize('en'), normalize('ENG'), normalize('deu'), normalize('de'), normalize('pt-BR')
    ('eng', 'eng', 'ger', 'ger', 'pob')
    """
    if code is None:
        return ''
    c = str(code).strip().lower().replace('_', '-')
    if not c:
        return ''
    if c in _SPECIAL_ALIASES:
        return _SPECIAL_ALIASES[c]
    if c in _PT_BR_ALIASES:
        return BRAZILIAN_PORTUGUESE
    if c in _CHINESE_SCRIPT_ALIASES:
        return 'chi'
    parts = c.split('-')
    primary = parts[0]
    if primary in ('pt', 'por') and len(parts) > 1 and parts[1] == 'br':
        return BRAZILIAN_PORTUGUESE
    if len(primary) == 2:
        return ISO639_1_TO_2B.get(primary, primary)
    if len(primary) == 3:
        return ISO639_2T_TO_2B.get(primary, LEGACY_TO_2B.get(primary, primary))
    # a typed language name ("Japanese") is accepted as a convenience
    if primary in NAME_TO_2B:
        return NAME_TO_2B[primary]
    return primary


def is_special(code):
    return normalize(code) in SPECIAL_CODES


def is_known(code):
    """True for the LPM special codes and for any code present in the Kodi language tables."""
    c = normalize(code)
    if c in SPECIAL_CODES or c == BRAZILIAN_PORTUGUESE:
        return True
    return c in LANGUAGE_NAMES or c in _SPINNER_LANG_3


def base_language(code):
    """Language without region ('pob' -> 'por')."""
    c = normalize(code)
    return 'por' if c == BRAZILIAN_PORTUGUESE else c


# ISO 3166-1 country codes, for regions read from titles and file names (where words like FULL, Sign or DD
# must not pass for a region); codes that are also common release words (AD, BD, CC, DD, HD, SD, TV ...) left out
_COUNTRIES = frozenset(
    'AE AF AG AI AL AM AO AQ AR AS AT AU AW AX AZ BA BB BE BF BG BH BI BJ BL BM BN BO BQ BR BS BT BV BW BY BZ CA CD CF '
    'CG CH CI CK CL CM CN CO CR CU CV CW CX CY CZ DE DJ DK DM DO DZ EC EE EG EH ER ES ET FI FJ FK FM FO FR GA GB GD GE '
    'GF GG GH GI GL GM GN GP GQ GR GS GT GU GW GY HK HM HN HR HT HU ID IE IL IM IN IO IQ IR IS IT JE JM JO JP KE KG KH '
    'KI KM KN KP KR KW KY KZ LA LB LC LI LK LR LS LT LU LV LY MA MC MD ME MF MG MH MK ML MM MN MO MP MQ MR MS MT MU MV '
    'MW MX MY MZ NA NC NE NF NG NI NL NO NP NR NU NZ OM PA PE PF PG PH PK PL PM PN PR PS PT PW PY QA RE RO RS RU RW SA '
    'SB SC SE SG SH SI SJ SK SL SM SN SO SR SS ST SV SX SY SZ TC TD TF TG TH TJ TK TL TM TN TO TR TT TW TZ UA UG UM US '
    'UY UZ VA VC VE VG VI VN VU WF WS YE YT ZA ZM ZW UK'.split())
_SCRIPTS = frozenset(('Hans', 'Hant', 'Latn', 'Cyrl'))


def plausible_region(region):
    """A region or script read from a title or a file name: a country, a UN region (419) or a known script."""
    return bool(region) and (region in _COUNTRIES or region in _SCRIPTS or (region.isdigit() and len(region) == 3))


def valid_region(region):
    """A region or script typed in a preference: as plausible_region(), and also the countries left out of
    _COUNTRIES (bn-BD is Bangladesh in a preference); not a made-up subtag such as FF."""
    return plausible_region(region) or region in ('AD', 'BD', 'CC', 'SD', 'TV')


def _canonical_region(base, subtag):
    """'au' -> 'AU', 'hant' -> 'Hant', '419' -> '419'; the region aliases of the language applied; '' if none."""
    t = (subtag or '').strip()
    if not t:
        return ''
    if t.isdigit():
        r = t
    elif len(t) == 4 and t.isalpha():
        r = t.title()
    elif len(t) in (2, 3) and t.isalpha():
        r = t.upper()
    else:
        return ''
    return _REGION_ALIASES.get(base, {}).get(r, r)


def parse_tag(code):
    """Any accepted code form -> (base language, region or script); region '' when there is none.

    >>> parse_tag('en-AU'), parse_tag('pob'), parse_tag('zh_TW'), parse_tag('eng'), parse_tag('es-MX')
    (('eng', 'AU'), ('por', 'BR'), ('chi', 'Hant'), ('eng', ''), ('spa', '419'))
    """
    if code is None:
        return ('', '')
    raw = str(code).strip().replace('_', '-')
    c = raw.lower()
    if not c:
        return ('', '')
    if c in _SPECIAL_ALIASES:
        return (_SPECIAL_ALIASES[c], '')
    if c in _PT_BR_ALIASES:
        return ('por', 'BR')
    if c in _CHINESE_SCRIPT_ALIASES:
        return ('chi', _CHINESE_SCRIPT_ALIASES[c])
    parts = raw.split('-')
    base = base_language(parts[0])
    for sub in parts[1:]:
        if sub.lower() in _SUBTITLE_FLAGS:          # en-HI, en-CC: hearing impaired / closed captions
            continue
        # region (AU), UN region (419), script (Hant), or a three letter alias of the language (zh-CHT)
        if (sub.isalpha() and len(sub) in (2, 4) or sub.isdigit()
                or sub.isalpha() and len(sub) == 3 and sub.upper() in _REGION_ALIASES.get(base, {})):
            region = _canonical_region(base, sub)
            if region:
                return (base, region)
    return (base, '')


def canonical_tag(code):
    """Canonical preference code, region kept: 'en-AU' -> 'eng-AU', 'pt-BR' -> 'pob', 'deu' -> 'ger'."""
    base, region = parse_tag(code)
    if not base:
        return ''
    if base == 'por' and region == 'BR':
        return BRAZILIAN_PORTUGUESE
    return '%s-%s' % (base, region) if region else base


def region_from_name(track_name, base=''):
    """Region or script named in a track title: 'English (Australia)' -> 'AU', 'Chinese Traditional' -> 'Hant'.

    Words of three letters or fewer count only when written in capitals ('US', 'BR', 'CHT'); a region that does
    not exist for the track's language is ignored ('pt' in a Portuguese title is Portugal, not in an English one).
    """
    if not track_name:
        return ''
    name = str(track_name)
    # a language tag in the title ('Portuguese (PT-BR)', 'es-419', 'zh_Hant'): its region, when it is a tag of
    # this language - its language part is never read as a region
    for m in _TITLE_TAG.finditer(name):
        lang, region = parse_tag(m.group(0))     # (parse_tag never takes HI / CC as a region)
        raw = m.group(0).replace('_', '-').split('-')[1]
        if region and (not base or lang == base) and plausible_region(_canonical_region('', raw)):
            return region
    if _LATIN_AMERICA.search(name) and (not base or base == 'spa'):
        return '419'
    for tok in _TITLE_TOKEN.findall(name):
        low = tok.lower()
        if len(tok) <= 3 and not (tok.isupper() or tok.isdigit()):
            continue
        for region, words in _TITLE_REGIONS:
            if low in words and (not base or base in _REGION_LANGUAGES.get(region, (base,))):
                return _REGION_ALIASES.get(base, {}).get(region, region)
    return ''


def stream_tag(stream):
    """(base language, region) of a stream dict: the tag first, the title for what the tag does not say."""
    if not stream:
        return ('', '')
    base, region = parse_tag(stream.get('language'))
    name = stream.get('name')
    if base in _NO_LANGUAGE:
        base, region = language_from_name(name), ''
    if base and not region and base not in SPECIAL_CODES:
        region = region_from_name(name, base)
    return (base, region)


def stream_code(stream):
    """Canonical code of a stream, region kept when known ('pob', 'eng-AU', 'ger') - what stored preferences save."""
    base, region = stream_tag(stream)
    if not base:
        return ''
    if base == 'por' and region == 'BR':
        return BRAZILIAN_PORTUGUESE
    return '%s-%s' % (base, region) if region else base


# Kodi (seen on 22) misreads an external subtitle file name with a BCP 47 tag, Movie.pt-BR.srt: it takes the
# last valid language code ('br' = Breton) as the language and puts the rest into the name ('pt (External)').
# A reported 'language' that is really the region, when Kodi did not keep it as a code:
_EXTERNAL_REGION_CODES = {'avt': 'AU'}
_EXTERNAL_LABEL = '(External)'


def _is_code(tok):
    c = normalize(tok)
    return c == BRAZILIAN_PORTUGUESE or c in _SPINNER_LANG_3 or (len(tok) == 3 and c in LANGUAGE_NAMES)


def external_name(stream, external_label=None):
    """The name of an external subtitle stream without Kodi's "(External)" label (localized label or the English
    one), or None when the stream is not external."""
    name = str((stream or {}).get('name') or '')
    labels = [l for l in (external_label, _EXTERNAL_LABEL) if l]
    if not any(l in name for l in labels):
        return None
    for l in labels:
        name = name.replace(l, ' ')
    return name


def repair_external(stream, external_label=None):
    """
    Language of an external subtitle as its file name says it. Returns the repaired code (e.g. 'pt-BR') or ''
    when the stream is not external or nothing needs repairing.

        Movie.pt-BR.srt -> Kodi: language 'br',  name 'pt (External)'   -> 'pt-BR'
        Movie.en-AU.srt -> Kodi: language 'avt', name 'en (External)'   -> 'en-AU'
        Movie.zh-Hant.srt -> Kodi: language 'zh', name 'Hant (External)' -> 'zh-Hant'
        Movie.es-419.srt -> Kodi: language 'es', name '419 (External)'   -> 'es-419'

    Rule: a lower case language code in the name is the real language, a capitalised token (GB, 419, Hant) in
    the name is the region or script; otherwise the reported language is the language, or the region when the
    name has the language (then a two letter code, or a known misread from _EXTERNAL_REGION_CODES).

    :param external_label: Kodi's localized "(External)" marker (string 21602); the English one always counts
    """
    rest = external_name(stream, external_label)
    if rest is None:
        return ''
    reported = str(stream.get('language') or '').strip()
    language, region = '', ''
    for tok in re.findall(r"[A-Za-z0-9]+", rest):
        if not language and tok.islower() and len(tok) in (2, 3) and _is_code(tok):
            language = tok
        elif not region and ((tok.isupper() and tok.isalpha() and len(tok) == 2) or (tok.isdigit() and len(tok) == 3)
                             or tok in _SCRIPTS):
            region = tok
    if not language and not region:
        return ''                          # the name holds no tag part: Kodi's language is right
    if not language:
        language, reported = reported, ''
        if not language:
            return ''
    if not region and reported:
        r = reported.lower()
        if r in _EXTERNAL_REGION_CODES:
            region = _EXTERNAL_REGION_CODES[r]
        elif len(r) == 2 and r.isalpha():
            region = r.upper()
    tag = language + ('-' + region if region else '')
    return tag if parse_tag(tag)[0] else ''


# subtitle files Kodi loads next to a video (Movie.<tag>[.forced][.sdh].<ext>; also ' ', '_', '-' after Movie)
# (the extensions Kodi loads as external subtitles; checked on Kodi 22: .text and .txt yes, .xml and .mpl no)
SUBTITLE_EXTENSIONS = frozenset(('.srt', '.ass', '.ssa', '.sub', '.idx', '.vtt', '.smi', '.sup', '.txt', '.text',
                                 '.utf', '.utf8', '.utf-8', '.rt', '.aqt', '.jss'))
_SUBTITLE_FLAGS = frozenset(('forced', 'sdh', 'hi', 'cc', 'default', 'foreign'))
_FILE_TOKEN = re.compile(r"[A-Za-z0-9]+")
# words Kodi leaves out of an external subtitle's name (Movie.pt-BR.forced.srt -> 'br', 'pt (External)')
_KODI_DROPPED = frozenset(('forced', 'default'))


def subtitle_file_tag(video_name, file_name):
    """
    Language tag a subtitle file name gives, for the video it belongs to; None when the file is not a subtitle of
    that video or names no language.

        ('Movie.mkv', 'Movie.pt-BR.forced.srt') -> {'tag': 'pt-BR', 'words': ['pt', 'br', 'forced']}
        ('Movie.mkv', 'Movie.por.BR.srt')       -> {'tag': 'por-BR', ...}
        ('Movie.mkv', 'Movie.srt')              -> None

    'words' are the lower case words of the part between the video name and the extension, in order: what Kodi
    spreads over the stream's language and name.
    """
    base = video_name.rsplit('.', 1)[0] if '.' in video_name else video_name
    stem, dot, ext = file_name.rpartition('.')
    if not dot or '.' + ext.lower() not in SUBTITLE_EXTENSIONS:
        return None
    # Kodi (22) loads Movie.pt-BR.srt, and also Movie pt-BR.srt, Movie_pt-BR.srt and Movie-pt-BR.srt
    if not stem.lower().startswith(base.lower()) or stem[len(base):len(base) + 1] not in ('.', ' ', '_', '-'):
        return None
    middle = stem[len(base) + 1:]
    parts = [x for x in re.split(r'[.\s]+', middle.replace('_', '-')) if x]
    # The part that names the language, in this order: a lower case code or tag (en, pt-BR) or a language name
    # (English); else a code in capitals of a common language (ENG, PT); else a flag word that is also a code
    # ('hi' is Hindi only when no other part names a language). Capitalised words that merely happen to be rare
    # language codes (War, Man, NEW) are never taken, as Kodi does not take them either.
    def rank(part):
        if part.lower() in _SUBTITLE_FLAGS:
            return 3 if _is_code(part) else 0
        lang_part = part.split('-')[0]
        lang = parse_tag(part)[0]
        if not lang or lang in SPECIAL_CODES:
            return 0
        if lang_part.islower() and _is_code(lang_part) or len(lang_part) > 3 and lang_part.lower() in NAME_TO_2B:
            return 1
        if lang_part.isupper() and len(lang_part) in (2, 3) and normalize(lang_part) in _SPINNER_LANG_3:
            return 2
        return 0
    ranked = sorted((r, n) for n, r in ((n, rank(p)) for n, p in enumerate(parts)) if r)
    if not ranked:
        return None
    n = ranked[0][1]
    part = parts[n]
    lang, region = parse_tag(part)
    tag = part
    if region and '-' in part and not plausible_region(_canonical_region(lang, part.split('-')[1])):
        tag, region = part.split('-')[0], ''         # Movie.en-FULL.srt: no region
    if not region and n + 1 < len(parts):            # Movie.por.BR.srt
        nxt = parts[n + 1]
        # a region in any case (Movie.pt.BR.srt, Movie.pt.br.srt), not a flag word
        if (nxt.lower() not in _SUBTITLE_FLAGS and plausible_region(_canonical_region(lang, nxt))
                and (len(nxt) == 2 and nxt.isalpha() or nxt.isdigit() or _canonical_region(lang, nxt) in _SCRIPTS)):
            tag = tag + '-' + nxt
    words = [t.lower() for t in _FILE_TOKEN.findall(middle)]
    return {'tag': tag, 'words': words}


def match_external_files(streams, file_tags, external_label=None):
    """
    Map Kodi's external subtitle streams onto the subtitle files of the video (see subtitle_file_tag()).

    Kodi builds an external stream's language and name from the words of the file name: one word (the last
    valid code) becomes the language, the other words, in order, the name (forced / default left out). A file
    fits a stream when its words are the stream's name words plus the reported language (in any code form, or
    kept whole: 'pt-BR'); failing that, the name words plus one word Kodi turned into another code ('in' ->
    'id', 'au' -> 'avt'). Files are then assigned step by step: a stream whose fitting files (those no other
    stream has taken) all carry one tag gets it; a stream still open gets the tag repair_external() reads, if
    one of its files has it.

    :param streams:   Kodi subtitle stream dicts
    :param file_tags: list of subtitle_file_tag() results
    :return: {stream index: tag}
    """
    candidates = {}
    for stream in streams or []:
        name = external_name(stream, external_label)
        if name is None:
            continue
        name_words = [w for w in (t.lower() for t in _FILE_TOKEN.findall(name)) if w not in _KODI_DROPPED]
        reported = str(stream.get('language') or '').lower()
        reported_words = _FILE_TOKEN.findall(reported)
        reported_code = normalize(reported) if reported and '-' not in reported else ''

        def fit(f):
            """2: the file's words are the stream's name plus its reported language; 1: the name plus one word
            (the one Kodi turned into another code: 'in' -> 'id', 'au' -> 'avt'); 0: no fit"""
            w = [x for x in f['words'] if x not in _KODI_DROPPED]
            n = len(reported_words)
            if n > 1:                    # kept whole as a tag of several words (Movie.pt_BR.srt -> 'pt-BR')
                for k in range(len(w) - n + 1):
                    if w[k:k + n] == reported_words and w[:k] + w[k + n:] == name_words:
                        return 2
            result = 0
            for k in range(len(w)):
                if w[:k] + w[k + 1:] == name_words:
                    if w[k] == reported or reported_code and normalize(w[k]) == reported_code:
                        return 2
                    # a word that is a language code itself would have been reported as one: then this file
                    # belongs to another stream (Movie.en.srt is not the file of 'cht', '(External)')
                    if not _is_code(w[k]):
                        result = 1
            return result

        fits = [fit(f) for f in file_tags]
        best = max(fits or [0])
        files = [n for n, score in enumerate(fits) if score and score == best]
        if files:
            candidates[stream['index']] = (files, stream, best)
    # streams with a full fit first, so a weak fit never takes their file
    candidates = dict(sorted(candidates.items(), key=lambda item: -item[1][2]))
    # assign step by step: a stream whose remaining files all carry one tag gets it, and a file that is the only
    # one left for a stream is taken; streams still open get the tag repair_external() reads, if a file has it
    result, taken = {}, set()
    progress = True
    while progress:
        progress = False
        for index, (files, stream, best) in candidates.items():
            if index in result:
                continue
            avail = [n for n in files if n not in taken]
            tags = set(canonical_tag(file_tags[n]['tag']) for n in avail)     # pt-BR = pt.br = pob
            if len(tags) == 1:
                result[index] = file_tags[avail[0]]['tag']
                if len(avail) == 1:
                    taken.add(avail[0])
                progress = True
        if progress:
            continue
        for index, (files, stream, best) in candidates.items():
            if index in result:
                continue
            guess = canonical_tag(repair_external(stream, external_label))
            avail = [n for n in files if n not in taken]
            hits = [n for n in avail if guess and canonical_tag(file_tags[n]['tag']) == guess]
            if hits:
                result[index] = file_tags[hits[0]]['tag']
                if len(hits) == 1:
                    taken.add(hits[0])
                progress = True
                break
    return result


def lang_matches(pref_code, stream_code):
    """Does a preference code match a stream's language code? (both accept any input form)"""
    p, pr = parse_tag(pref_code)
    s, sr = parse_tag(stream_code)
    if not p or not s or p != s:
        return False
    # a plain preference accepts every region; a regional one also accepts a track of unknown region
    return not pr or not sr or pr == sr


def aliases(code):
    """All known spellings of a language, canonical first: 'ger' -> ('ger', 'deu', 'de')."""
    c = normalize(code)
    if not c:
        return ()
    out = [c]
    for extra in (_B_TO_T.get(c), _B_TO_A2.get(c)):
        if extra and extra not in out:
            out.append(extra)
    if c == BRAZILIAN_PORTUGUESE:
        out.extend(('pt-br',))
    return tuple(out)


def display_name(code):
    """English name for logging / preference tuples ('ger' -> 'German')."""
    c = normalize(code)
    if c in _SPECIAL_NAMES:
        return _SPECIAL_NAMES[c]
    base, region = parse_tag(code)
    name = LANGUAGE_NAMES.get(base, base)
    if region:
        return '%s (%s)' % (name, _REGION_NAMES.get(region, region))
    return name


def describe(code):
    """'ger' -> 'ger/deu/de (German)' - for log lines."""
    c = normalize(code)
    if not c:
        return "''"
    region = parse_tag(code)[1]
    return '%s%s (%s)' % ('/'.join(aliases(c)), '-' + region if region and c != BRAZILIAN_PORTUGUESE else '',
                          display_name(code))


def from_spinner(value):
    """Settings spinner value (LANGUAGES column 4) -> (english name, canonical code); ('', '') if unknown."""
    row = _SPINNER_NAMES.get(str(value).strip()) if value is not None else None
    if not row:
        return ('', '')
    return (row[0], canonical_tag(row[3].split(',')[0]))


def normalize_list(codes):
    """Normalise a list of codes (e.g. the Original audio list) with canonical_tag() (region kept: pt-BR -> pob,
    en-AU -> eng-AU); drops empties and duplicates, keeps 'any'."""
    out = []
    for code in codes or []:
        c = canonical_tag(code)
        if c and c not in out:
            out.append(c)
    return out


def language_from_name(track_name):
    """Best-effort language of a track from its title, e.g. 'English SDH' -> 'eng'.

    Whole words only (so 'en' can never match inside 'French'), and 2 letter words are ignored because they
    are far too ambiguous in free text ('it', 'is', 'no', 'he'...). Used ONLY when the stream carries no
    usable language tag.
    """
    if not track_name:
        return ''
    for tok in _WORD.findall(str(track_name).lower()):
        b = NAME_TO_2B.get(tok)
        if b:
            return b
        if len(tok) == 3:
            c = normalize(tok)
            if c in _SPINNER_LANG_3:
                return c
    return ''


def effective_language(stream):
    """Canonical language of an audio/subtitle stream dict (tag first, then track title)."""
    if not stream:
        return ''
    lang = normalize(stream.get('language'))
    if lang not in _NO_LANGUAGE:
        return lang
    return language_from_name(stream.get('name'))


def _special_matches(c, stream, track_type):
    name_l = str(stream.get('name') or '').lower()
    s = normalize(stream.get('language'))
    if c == ANY:
        return True
    if c == ORG:
        if track_type == 'Audio':
            return bool(stream.get('isoriginal', False)) or s == ORG
        return s == ORG or 'original' in name_l
    if c == UNK:
        return s in (UNK, '') or 'unknown' in name_l
    if c == UND:
        return s in (UND, '')
    return False                          # "None" is handled by the callers, it never matches a track


def match_score(code, stream, track_type='Audio'):
    """
    How well a stream fits a preference code: 2 = language and region match, 1 = the language matches (one side
    has no region), 0 = no match. See the module docstring.

    :param code:       preference code in any accepted form (en, eng, en-AU, pob ...), or an LPM special code
    :param stream:     Kodi audio/subtitle stream dict ('language', 'name', 'isoriginal', ...)
    :param track_type: 'Audio' or 'Subtitle'
    """
    base, region = parse_tag(code)
    if not base or not stream:
        return 0                          # an empty code must never match anything
    if base in SPECIAL_CODES:
        return 1 if _special_matches(base, stream, track_type) else 0
    s_base, s_region = stream_tag(stream)
    if not s_base or s_base != base:
        return 0
    if not region or not s_region:
        return 1
    return 2 if region == s_region else 0


def stream_matches_language(code, stream, track_type='Audio'):
    """Does a preference code match a stream at all? (match_score() > 0)"""
    return match_score(code, stream, track_type) > 0


def best_matches(code, streams, track_type='Audio'):
    """Indexes of the streams with the best match score for code (first stream first); [] when none matches."""
    best, out = 0, []
    for stream in streams or []:
        score = match_score(code, stream, track_type)
        if score > best:
            best, out = score, [stream['index']]
        elif score and score == best:
            out.append(stream['index'])
    return out

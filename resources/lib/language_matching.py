# -*- coding: utf-8 -*-

"""Language/locale matching helpers which do not depend on Kodi.

Containers and Kodi often expose only a legacy ISO 639 code even when several
regional or script variants exist.  This module turns BCP-47 codes and common
track-title labels into a small, extensible set of normalized variants.
"""

import re
import unicodedata


LANGUAGE_BASE_ALIASES = {
    "fr": {"fr", "fre", "fra", "french", "francais"},
    "es": {"es", "spa", "spanish", "espanol", "castellano"},
    "pt": {"pt", "pb", "por", "portuguese", "portugues"},
    "zh": {"zh", "chi", "zho", "chinese", "中文"},
    "en": {"en", "eng", "english"},
}

# Variant recognition is data-driven. ``codes`` contains BCP-47 forms commonly
# emitted by tools; ``aliases`` contains normalized words seen in track titles.
VARIANTS = {
    "fr-ca": {
        "base": "fr", "codes": {"fr-ca", "fre-ca", "fra-ca", "fre-can", "fra-can"},
        "short_codes": {"ca", "can"},
        "aliases": {"canada", "canadian", "canadien", "canadienne", "quebec",
                    "quebecois", "quebecoise", "vfq", "vfc"},
    },
    "fr-fr": {
        "base": "fr", "codes": {"fr-fr", "fre-fr", "fra-fr", "fre-fra", "fra-fra"},
        "short_codes": {"fr", "fra"},
        "aliases": {"france", "french european", "european french", "metropolitan",
                    "metropolitain", "metropolitaine", "truefrench", "true french",
                    "vff", "vf2"},
    },
    "es-419": {
        "base": "es", "codes": {"es-419", "es-mx"},
        "short_codes": {"419", "mx"},
        "aliases": {"419", "latin america", "latin american", "latinoamerica",
                    "latinoamericano", "latinoamericana", "latam", "latino",
                    "mexico", "mexican"},
    },
    "es-es": {
        "base": "es", "codes": {"es-es"},
        "short_codes": {"es", "esp"},
        "aliases": {"espana", "spain", "spanish european", "european spanish"},
    },
    "pt-br": {
        "base": "pt", "codes": {"pt-br"},
        "short_codes": {"br", "bra"},
        "aliases": {"brasil", "brazil", "brazilian", "brasileiro", "brasileira"},
    },
    "pt-pt": {
        "base": "pt", "codes": {"pt-pt"},
        "short_codes": {"pt", "prt"},
        "aliases": {"portugal", "portuguese european", "european portuguese"},
    },
    "zh-hans": {
        "base": "zh", "codes": {"zh-hans", "zh-cn", "zh-sg"},
        "short_codes": {"hans", "cn", "sg"},
        "aliases": {"simplified", "simplified chinese", "简体", "簡体", "chs"},
    },
    "zh-hant": {
        "base": "zh", "codes": {"zh-hant", "zh-tw", "zh-hk", "zh-mo"},
        "short_codes": {"hant", "tw", "hk", "mo"},
        "aliases": {"traditional", "traditional chinese", "繁體", "繁体", "cht"},
    },
    "en-us": {
        "base": "en", "codes": {"en-us"},
        "short_codes": {"us", "usa"},
        "aliases": {"united states", "american", "us english"},
    },
    "en-gb": {
        "base": "en", "codes": {"en-gb", "en-uk"},
        "short_codes": {"gb", "uk", "gbr"},
        "aliases": {"united kingdom", "british", "uk english", "great britain"},
    },
}


def _normalized_words(value):
    value = unicodedata.normalize("NFKD", value or "")
    value = "".join(char for char in value if not unicodedata.combining(char))
    # Keep CJK characters: ``\w`` is Unicode-aware in Python 3.
    return " ".join(re.sub(r"[^\w]+", " ", value.casefold()).split())


def _normalized_code(value):
    return re.sub(r"_", "-", (value or "").strip().casefold())


def _language_base(value):
    normalized = _normalized_words(value)
    first_code_part = _normalized_code(value).split("-", 1)[0]
    for base, aliases in LANGUAGE_BASE_ALIASES.items():
        if normalized in aliases or first_code_part in aliases:
            return base
    return None


def _variant(value, expected_base=None):
    raw_code = _normalized_code(value)
    words = _normalized_words(value)
    padded_words = " " + words + " "
    found = []

    for variant, definition in VARIANTS.items():
        if expected_base and definition["base"] != expected_base:
            continue
        code_found = any(re.search(r"(?:^|[^a-z0-9])" + re.escape(code) +
                                   r"(?:$|[^a-z0-9])", raw_code)
                         for code in definition["codes"])
        short_code_found = any(re.search(r"[\(\{\[]\s*" + re.escape(code) + r"\s*[\)\}\]]",
                                         raw_code)
                               for code in definition.get("short_codes", set()))
        alias_found = any(" " + alias + " " in padded_words
                          for alias in definition["aliases"])
        if code_found or short_code_found or alias_found:
            found.append(variant)

    return found[0] if len(found) == 1 else None


def language_match_score(preference_name, preference_code, stream_language, stream_name=""):
    """Score a stream against a language preference.

    0 means no match. 300 is an exact locale/script variant, 200 is a stream
    whose base language matches but whose variant is unknown, and 100 is the
    historical generic language match.
    """
    preference_name = preference_name or ""
    preference_code = preference_code or ""
    stream_language = stream_language or ""

    preference_codes = [_normalized_code(code) for code in preference_code.split(",")]
    # A regional entry from Kodi settings also contains its generic ISO code.
    # Treat those as one preference so the generic alias cannot bypass the region.
    preferred_variant = next((variant for code in preference_codes
                              for variant in [_variant(code)] if variant), None)
    preferred_variant = preferred_variant or _variant(preference_name)
    preferred_base = (VARIANTS[preferred_variant]["base"] if preferred_variant else
                      next((base for code in preference_codes
                            for base in [_language_base(code)] if base), None))
    preferred_base = preferred_base or _language_base(preference_name)

    # Languages without declared variants keep the add-on's exact legacy match.
    if preferred_base is None:
        return 100 if _normalized_code(stream_language) in preference_codes or preference_name.casefold() == stream_language.casefold() else 0

    stream_base = _language_base(stream_language)
    if stream_base != preferred_base:
        return 0

    # A base-language preference intentionally matches every regional variant.
    if preferred_variant is None:
        return 100

    # Prefer a structured code from Kodi, then infer from the human title.
    stream_variant = (_variant(stream_language, stream_base) or
                      _variant(stream_name, stream_base))
    if stream_variant == preferred_variant:
        return 300
    if stream_variant is None:
        return 200
    return 0

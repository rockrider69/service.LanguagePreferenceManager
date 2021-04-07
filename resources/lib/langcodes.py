# -*- coding: utf-8 -*- 

#    This script is based on the one of script.xbmc.subtitles
#    Thanks to their original authors amet, mr_blobby



LANGUAGES      = (
    
    # Full Language name[0]     podnapisi[1]  ISO 639-1[2]   ISO 639-1 Code[3]   Script Setting Language[4]   localized name id number[5]
    
    ("Albanian"                   , "29",       "sq",            "alb",                 "0",                     30201  ),
    ("Arabic"                     , "12",       "ar",            "ara",                 "1",                     30202  ),
    ("Belarusian"                 , "0" ,       "hy",            "arm",                 "2",                     30203  ),
    ("Bosnian"                    , "10",       "bs",            "bos",                 "3",                     30204  ),
    ("Bulgarian"                  , "33",       "bg",            "bul",                 "4",                     30205  ),
    ("Catalan"                    , "53",       "ca",            "cat",                 "5",                     30206  ),
    ("Chinese"                    , "17",       "zh",            "chi",                 "6",                     30207  ),
    ("Croatian"                   , "38",       "hr",            "hrv",                 "7",                     30208  ),
    ("Czech"                      , "7",        "cs",            "cze",                 "8",                     30209  ),
    ("Danish"                     , "24",       "da",            "dan",                 "9",                     30210  ),
    ("Dutch"                      , "23",       "nl",            "dut",                 "10",                    30211  ),
    ("English"                    , "2",        "en",            "eng",                 "11",                    30212  ),
    ("Estonian"                   , "20",       "et",            "est",                 "12",                    30213  ),
    ("Finnish"                    , "31",       "fi",            "fin",                 "13",                    30214  ),
    ("French"                     , "8",        "fr",            "fre",                 "14",                    30215  ),
    ("German"                     , "5",        "de",            "ger,deu",             "15",                    30216  ),
    ("Greek"                      , "16",       "el",            "ell",                 "16",                    30217  ),
    ("Hebrew"                     , "22",       "he",            "heb",                 "17",                    30218  ),
    ("Hindi"                      , "42",       "hi",            "hin",                 "18",                    30219  ),
    ("Hungarian"                  , "15",       "hu",            "hun",                 "19",                    30220  ),
    ("Icelandic"                  , "6",        "is",            "ice",                 "20",                    30221  ),
    ("Indonesian"                 , "0",        "id",            "ind",                 "21",                    30222  ),
    ("Italian"                    , "9",        "it",            "ita",                 "22",                    30223  ),
    ("Japanese"                   , "11",       "ja",            "jpn",                 "23",                    30224  ),
    ("Korean"                     , "4",        "ko",            "kor",                 "24",                    30225  ),
    ("Latvian"                    , "21",       "lv",            "lav",                 "25",                    30226  ),
    ("Lithuanian"                 , "0",        "lt",            "lit",                 "26",                    30227  ),
    ("Macedonian"                 , "35",       "mk",            "mac",                 "27",                    30228  ),
    ("Norwegian"                  , "3",        "no",            "nor",                 "28",                    30229  ),
    ("Persian"                    , "52",       "fa",            "per",                 "29",                    30230  ),
    ("Polish"                     , "26",       "pl",            "pol",                 "30",                    30231  ),
    ("Portuguese"                 , "32",       "pt",            "por",                 "31",                    30232  ),
    ("Portuguese (Brazil)"        , "48",       "pb",            "pt-br",               "32",                    30233  ),
    ("Romanian"                   , "13",       "ro",            "rum",                 "33",                    30234  ),
    ("Russian"                    , "27",       "ru",            "rus",                 "34",                    30235  ),
    ("Serbian"                    , "36",       "sr",            "scc",                 "35",                    30236  ),
    ("Slovak"                     , "37",       "sk",            "slo",                 "36",                    30237  ),
    ("Slovenian"                  , "1",        "sl",            "slv",                 "37",                    30238  ),
    ("Spanish"                    , "28",       "es",            "spa",                 "38",                    30239  ),
    ("Swedish"                    , "25",       "sv",            "swe",                 "39",                    30240  ),
    ("Thai"                       , "0",        "th",            "tha",                 "40",                    30241  ),
    ("Turkish"                    , "30",       "tr",            "tur",                 "41",                    30242  ),
    ("Ukrainian"                  , "46",       "uk",            "ukr",                 "42",                    30243  ),
    ("Vietnamese"                 , "51",       "vi",            "vie",                 "43",                    30244  ),
    ("BosnianLatin"               , "10",       "bs",            "bos",                 "100",                   30245  ),
    ("Farsi"                      , "52",       "fa",            "per",                 "13",                    30246  ),
    ("English (US)"               , "2",        "en",            "eng",                 "100",                   30212  ),
    ("English (UK)"               , "2",        "en",            "eng",                 "100",                   30212  ),
    ("Portuguese (Brazilian)"     , "48",       "pt-br",         "pob",                 "100",                   30234  ),
    ("Portuguese (Brazil)"        , "48",       "pb",            "pob",                 "32",                    30234  ),
    ("Portuguese-BR"              , "48",       "pb",            "pob",                 "32",                    30234  ),
    ("Brazilian"                  , "48",       "pb",            "pob",                 "32",                    30234  ),
    ("Español (Latinoamérica)"    , "28",       "es",            "spa",                 "100",                   30240  ),
    ("Español (España)"           , "28",       "es",            "spa",                 "100",                   30240  ),
    ("Spanish (Latin America)"    , "28",       "es",            "spa",                 "100",                   30240  ),
    ("Español"                    , "28",       "es",            "spa",                 "100",                   30240  ),
    ("SerbianLatin"               , "36",       "sr",            "scc",                 "100",                   30237  ),
    ("Spanish (Spain)"            , "28",       "es",            "spa",                 "100",                   30240  ),
    ("Chinese (Traditional)"      , "17",       "zh",            "chi",                 "100",                   30207  ),
    ("Chinese (Simplified)"       , "17",       "zh",            "chi",                 "100",                   30207  ),
    ("None"                       , "-1",       "",              "non",                 "44",                    30200  ) )

def languageTranslate(lang, lang_from, lang_to):
  for x in LANGUAGES:
    codes = x[lang_from].split(r',')
    for code in codes:
      if lang == code :
        return x[lang_to]

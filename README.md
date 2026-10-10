service.LanguagePreferenceManager
=================================

A manager for audio and subtitle preferences
============================================

This addon provides an easy way to set your preferred audio streams and subtitle languages in Kodi.

You can select which audio tracks and subtitles to automatically activate based on your priorities, and define simple conditional rules like "if audio is xxx then activate subtitles yyy" via drop/down lists.
More advanced custom rules can be defined as well (see changelog for more on the syntax. Note that custom rules always take precedence over others).

Special language codes None(non) for subtitles and Any(any) for audio can be used in Conditional Subtitles Rules, normal or custom.
For example "fre:non>any:fre>any:eng" will disable subtitles if audio is French (except if a french forced subtitles track exists) and activate french subtitles for any other audio language. If these are not available it will try the same finding english subtitles.

Rules are re-evaluated and applied whenever you switch audio while watching (from v0.1.5).

It's now also possible to force ignore "Signs and Songs" subtitles in preferences evaluations, based on name, and/or any other subtitle tracks based on predefined keywords.
For example, most dual audio Anime provides english and japanese audio and two english subtitles. Dialogue subtitles with all the dialogue to go with the japanese audio and Song/Sign subtitles which only translate song lyrics and signs you see on screen to be used with the english audio stream. Previously the addon just picked the first subtitles with the correct language which weren't always the correct ones.

An option allows you to store forced preferences per Movie / TVshow (from v1.0.6). When you manually change audio and/or subtitle tracks during play, this will be saved as an overriding preference, taking precedence over all other rules for the next opening of the Movie, or the next episode of the TVshow (Thx a lot to SgtJalau!)

Special Thanks
==============

- @ace20022 and @scott967 for initial development

- @cyberden for making this addon ready for Kodi Matrix

- @fpatrick for fixing an issue with language mapping

- @KnappeGEIL for ideas how to ignore 'Signs and Songs' subtitles

- @SgtJalau for the complete feature to store specific/overriding preferences per Movie / TVshow

## Language codes (2.0.1)
Everywhere a language code can be typed (custom preferences, Original audio list) you can use 2-letter (`en`, `ja`, `de`), 3-letter (`eng`, `jpn`, `ger` or `deu`) codes, or BCP47-style tags (`pt-BR`); they are all treated as the same language. Kodi 22 reports 2-letter codes for streams, older Kodi versions 3-letter ones - both are matched.

## Selection priority
Stored media preferences (`Store preferences`: the audio/subtitle tracks you chose manually for a movie or episode) rank above everything else and are the only thing that outranks the regex filter. What a stored preference applied is never changed by the rules below; if only part of it fits the file (e.g. its subtitle language is missing), only the other part falls through to them.

Subtitles (initial run):
1. Regex subtitle filter (if enabled) - nothing below can override a regex match
2. Conditional subtitle preferences (if enabled) - used when the regex found nothing (they follow the audio track, also when you change it later)
3. Normal subtitle preferences rank below the conditional rules and are skipped when the regex filter matched
4. Subtitle tag in the file name (`Use filename`, e.g. `.subtitle-2`) - lowest preference, only if nothing above selected a track
5. Default subtitle, else the first valid one - when nothing above selected a track (only with the regex filter or conditional subtitles enabled)

Audio: audio preferences first; an audio tag in the file name (`.audiostream-1`) is only used when the audio preferences matched nothing.

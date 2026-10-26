"""
The words a user adds to a regex subtitle filter profile (a comma separated list) as a pattern, and the filter that
uses the built-in pattern of the profile and the added words together. The built-in pattern itself is never changed.
"""
import re

# what stands between the words of an added phrase in a track title: spaces, dots, dashes, underscores ...
_SEPARATOR = r'[\s._+\-\/\\]+'
# the same test the built-in Signs & Songs part uses for a whole word: no letter right before / after
_NO_LETTER_BEFORE = r'(?<![^\W\d_])'
_NO_LETTER_AFTER = r'(?![^\W\d_])'


def parse_words(text):
    """['karaoke', 'closed captions'] of 'Karaoke , closed  captions,, KARAOKE': trimmed, no empty entries, no
    duplicates (the case does not count), in the order given."""
    words, seen = [], set()
    for entry in (text or '').split(','):
        word = ' '.join(entry.split())
        if word and word.lower() not in seen:
            seen.add(word.lower())
            words.append(word)
    return words


def words_pattern(words, whole_word):
    """The regex source for the added words; '' without words. Special characters are taken as written, a space in
    a phrase matches any run of spaces, dots, dashes or underscores. whole_word: no letter right before or after."""
    alternatives = [_SEPARATOR.join(re.escape(token) for token in word.split(' ')) for word in words]
    if not alternatives:
        return ''
    body = '(?:{0})'.format('|'.join(alternatives))
    if whole_word:
        body = _NO_LETTER_BEFORE + body + _NO_LETTER_AFTER
    return '(?i:{0})'.format(body)


class RegexFilter:
    """search / finditer of the built-in pattern of a profile and of the added words: a title is a hit when either
    one hits."""

    def __init__(self, base=None, extra=None):
        self.parts = [p for p in (base, extra) if p is not None]

    def search(self, text):
        for part in self.parts:
            found = part.search(text)
            if found:
                return found
        return None

    def finditer(self, text):
        for part in self.parts:
            for found in part.finditer(text):
                yield found

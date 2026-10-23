"""
The format of subtitle tracks, for the subtitle format preference (settings SubFormat1..3, the conditional rules' format,
the regex filter's format choice): which of srt, ass, webvtt, pgs, vobsub a subtitle is.

Kodi does not report the codec of a subtitle (JSON-RPC and the info labels give a subtitle's language and name only).
For a Matroska (.mkv) file the Tracks element of the header lists every track with its CodecID in the order Kodi
numbers the embedded subtitle streams: a few kB read through a small reader object (read(n) -> bytes, seek(pos)),
Kodi's file layer in the add-on (so smb:// nfs:// ... work too), a plain file in tests. An external subtitle file is told
by its extension, a track by a format word in its title.

Nothing here reads subtitle text or converts anything.
"""
import re

_EBML_HEADER = 0x1A45DFA3
_SEGMENT = 0x18538067
_SEEK_HEAD = 0x114D9B74
_SEEK = 0x4DBB
_SEEK_ID = 0x53AB
_SEEK_POSITION = 0x53AC
_TRACKS = 0x1654AE6B
_CLUSTER = 0x1F43B675
_TRACK_ENTRY = 0xAE
_TRACK_TYPE = 0x83
_CODEC_ID = 0x86
_CODEC_PRIVATE = 0x63A2
_SUBTITLE_TYPE = 17

_MAX_ELEMENTS = 500            # top level elements looked at before giving up
_MAX_TRACKS_BYTES = 4 << 20    # a Tracks element is a few kB; anything this big is not a header
_MAX_SEEK_HEAD_BYTES = 1 << 20


class _Reader:
    """Kodi's xbmcvfs.File (or any object with readBytes / read and seek) as read(n) / seek(pos)."""

    def __init__(self, handle):
        self.h = handle

    def read(self, n):
        fn = getattr(self.h, 'readBytes', None)
        data = fn(n) if fn else self.h.read(n)
        return bytes(data) if data else b''

    def seek(self, pos):
        self.h.seek(pos, 0)

    def close(self):
        self.h.close()


def _vint(data, pos, keep_marker):
    """(value, length) of the EBML variable length integer at pos, (None, 0) when it is not complete / valid.
    An all-ones size (unknown size) is returned as -1."""
    if pos >= len(data):
        return None, 0
    first = data[pos]
    length = 1
    mask = 0x80
    while length <= 8 and not first & mask:
        length += 1
        mask >>= 1
    if length > 8 or pos + length > len(data):
        return None, 0
    value = first if keep_marker else first & (mask - 1)
    for b in data[pos + 1:pos + length]:
        value = (value << 8) | b
    if not keep_marker and value == (1 << (7 * length)) - 1:
        return -1, length
    return value, length


def _header(reader, pos):
    """(id, size, header length) of the element at pos in the file, or None."""
    reader.seek(pos)
    data = reader.read(16)
    eid, n1 = _vint(data, 0, True)
    if eid is None:
        return None
    size, n2 = _vint(data, n1, False)
    if size is None:
        return None
    return eid, size, n1 + n2


def _children(data):
    """(id, payload bytes) of the elements in data."""
    pos = 0
    while pos < len(data):
        eid, n1 = _vint(data, pos, True)
        if eid is None:
            return
        size, n2 = _vint(data, pos + n1, False)
        if size is None or size < 0:
            return
        start = pos + n1 + n2
        yield eid, data[start:start + size]
        pos = start + size


def _uint(payload):
    return int.from_bytes(payload, 'big')


def _subtitle_codecs(tracks):
    codecs = []
    for eid, entry in _children(tracks):
        if eid != _TRACK_ENTRY:
            continue
        kind, codec = None, ''
        for cid, payload in _children(entry):
            if cid == _TRACK_TYPE:
                kind = _uint(payload)
            elif cid == _CODEC_ID:
                codec = payload.decode('ascii', 'replace').rstrip('\0')
        if kind == _SUBTITLE_TYPE:
            codecs.append(codec)
    return codecs


def matroska_subtitle_codecs(reader):
    """CodecIDs of the subtitle tracks of the Matroska file behind reader, in track order ('S_TEXT/ASS',
    'S_TEXT/UTF8', 'S_HDMV/PGS', 'S_VOBSUB' ...); None when the file is no Matroska file or has no readable
    Tracks header (an empty list: a Matroska file without subtitles)."""
    top = _header(reader, 0)
    if not top or top[0] != _EBML_HEADER or top[1] < 0:
        return None
    pos = top[2] + top[1]
    seg = _header(reader, pos)
    if not seg or seg[0] != _SEGMENT:
        return None
    seg_data = pos + seg[2]              # SeekPosition values count from here
    pos = seg_data
    tracks_at = None
    for _ in range(_MAX_ELEMENTS):
        el = _header(reader, pos)
        if not el:
            return None
        eid, size, hlen = el
        if eid == _TRACKS:
            if size < 0 or size > _MAX_TRACKS_BYTES:
                return None
            reader.seek(pos + hlen)
            return _subtitle_codecs(reader.read(size))
        if eid == _CLUSTER:
            if tracks_at is None:
                return None
            el = _header(reader, seg_data + tracks_at)
            if not el or el[0] != _TRACKS or el[1] < 0 or el[1] > _MAX_TRACKS_BYTES:
                return None
            reader.seek(seg_data + tracks_at + el[2])
            return _subtitle_codecs(reader.read(el[1]))
        if size < 0:
            return None
        if eid == _SEEK_HEAD and size <= _MAX_SEEK_HEAD_BYTES:
            reader.seek(pos + hlen)
            for sid, entry in _children(reader.read(size)):
                if sid != _SEEK:
                    continue
                fields = dict(_children(entry))
                if _uint(fields.get(_SEEK_ID, b'')) == _TRACKS and _SEEK_POSITION in fields:
                    tracks_at = _uint(fields[_SEEK_POSITION])
            if tracks_at is not None:
                pos = seg_data + tracks_at          # straight to the Tracks element
                continue
        pos += hlen + size
    return None


def subtitle_codecs(path):
    """Subtitle CodecIDs of the video at path (a Kodi path: local, smb://, nfs:// ...), None when unreadable or
    not Matroska."""
    try:
        import xbmcvfs
        handle = xbmcvfs.File(path)
    except Exception:
        return None
    try:
        return matroska_subtitle_codecs(_Reader(handle))
    except Exception:
        return None
    finally:
        try:
            handle.close()
        except Exception:
            pass


def is_ass(codec):
    """True for the Advanced SubStation Alpha codecs (S_TEXT/ASS, S_TEXT/SSA, and the old S_ASS / S_SSA)."""
    c = (codec or '').upper()
    return c.startswith(('S_TEXT/ASS', 'S_TEXT/SSA', 'S_ASS', 'S_SSA'))


def is_webvtt(codec):
    return (codec or '').upper().startswith(('S_TEXT/WEBVTT', 'D_WEBVTT'))


# The subtitle formats a user can rank (settings SubFormat1..3: value n = SUBTITLE_FORMATS[n - 1], 0 = none)
SUBTITLE_FORMATS = ('srt', 'ass', 'webvtt', 'pgs', 'vobsub')

_EXTENSION_FORMATS = {'.srt': 'srt', '.ass': 'ass', '.ssa': 'ass', '.vtt': 'webvtt', '.sup': 'pgs', '.idx': 'vobsub'}
# format words in a track title: "English [SRT]", "Signs (ASS)", "PGS", "SubRip" ...
_NAME_FORMATS = (('srt', re.compile(r'(?<![A-Za-z0-9])(?:srt|subrip)(?![A-Za-z0-9])', re.I)),
                 ('ass', re.compile(r'(?<![A-Za-z0-9])(?:ass|ssa)(?![A-Za-z0-9])', re.I)),
                 ('webvtt', re.compile(r'(?<![A-Za-z0-9])(?:web)?vtt(?![A-Za-z0-9])', re.I)),
                 ('pgs', re.compile(r'(?<![A-Za-z0-9])(?:pgs|sup)(?![A-Za-z0-9])', re.I)),
                 ('vobsub', re.compile(r'(?<![A-Za-z0-9])(?:vobsub|idx)(?![A-Za-z0-9])', re.I)))


def format_of_codec(codec):
    """The ranked format ('srt', 'ass', 'webvtt', 'pgs', 'vobsub') of a Matroska CodecID, None for any other."""
    c = (codec or '').upper()
    if c.startswith(('S_TEXT/UTF8', 'S_TEXT/ASCII')):
        return 'srt'
    if is_ass(c):
        return 'ass'
    if is_webvtt(c):
        return 'webvtt'
    if c.startswith('S_HDMV/PGS'):
        return 'pgs'
    if c.startswith('S_VOBSUB'):
        return 'vobsub'
    return None


def format_of_extension(extension):
    """The ranked format of a subtitle file's extension ('.srt', 'ass'), None when it names none ('.sub' may be
    MicroDVD text or VobSub pictures: unknown)."""
    e = (extension or '').lower()
    return _EXTENSION_FORMATS.get(e if e.startswith('.') else '.' + e)


def format_of_name(name):
    """The ranked format a track title names ('English [SRT]'), None when it names none or several."""
    found = [fmt for fmt, pattern in _NAME_FORMATS if pattern.search(name or '')]
    return found[0] if len(found) == 1 else None

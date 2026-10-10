"""
Codec of the embedded subtitle tracks of a video file, which Kodi does not report (JSON-RPC and the info labels
give a subtitle's language and name only).

Only Matroska (.mkv) is read: the Tracks element of the header lists every track with its CodecID in the order
Kodi numbers the embedded subtitle streams. Reading goes through a small reader object (read(n) -> bytes,
seek(pos)), Kodi's file layer in the add-on (so smb:// nfs:// ... work too), a plain file in tests.
"""

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


class _Buffered:
    """read(n) / seek(pos) on top of a reader, fetching _CHUNK bytes at a time. The converter walks the element
    headers of the whole file (a few hundred bytes of every video / audio block); a read per header is one round
    trip each over nfs / smb / http (tens of thousands of them), a few large sequential reads are what a demuxer
    such as ffmpeg does, and as fast as the link can carry the file."""
    _CHUNK = 4 << 20

    def __init__(self, reader):
        self.r = reader
        self.start = 0
        self.buf = b''
        self.pos = 0

    def seek(self, pos):
        self.pos = pos

    def read(self, n):
        end = self.pos + n
        if not (self.start <= self.pos and end <= self.start + len(self.buf)):
            self.r.seek(self.pos)
            data = self.r.read(max(n, self._CHUNK))
            if not data:
                return b''
            self.start, self.buf = self.pos, data
        out = self.buf[self.pos - self.start:end - self.start]
        self.pos += len(out)
        return out


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


def is_convertible(codec):
    """True for the text subtitle formats the sub converter turns into SRT: everything but SRT itself (S_TEXT/UTF8)
    and the picture formats (PGS / SUP, VobSub, DVB), which hold bitmaps and would need OCR."""
    return is_ass(codec) or is_webvtt(codec)


def is_bitmap(codec):
    c = (codec or '').upper()
    return c.startswith(('S_HDMV/PGS', 'S_VOBSUB', 'S_DVBSUB', 'S_IMAGE'))


# ---------------------------------------------------------------------------------------------------------------
# The events (text and timing) of one embedded subtitle track, for the sub converter

_INFO = 0x1549A966
_TIMESTAMP_SCALE = 0x2AD7B1
_TRACK_NUMBER = 0xD7
_CLUSTER_TIMESTAMP = 0xE7
_SIMPLE_BLOCK = 0xA3
_BLOCK_GROUP = 0xA0
_BLOCK = 0xA1
_BLOCK_DURATION = 0x9B
_DEFAULT_DURATION_MS = 3000


def _subtitle_tracks(tracks):
    """[(track number, CodecID, CodecPrivate bytes)] of the subtitle tracks, in track order."""
    found = []
    for eid, entry in _children(tracks):
        if eid != _TRACK_ENTRY:
            continue
        number, kind, codec, private = None, None, '', b''
        for cid, payload in _children(entry):
            if cid == _TRACK_NUMBER:
                number = _uint(payload)
            elif cid == _TRACK_TYPE:
                kind = _uint(payload)
            elif cid == _CODEC_ID:
                codec = payload.decode('ascii', 'replace').rstrip('\0')
            elif cid == _CODEC_PRIVATE:
                private = payload
        if kind == _SUBTITLE_TYPE and number is not None:
            found.append((number, codec, private))
    return found


def _block(payload, track):
    """(relative timestamp in ticks, data) of a Block / SimpleBlock payload of the given track, else None."""
    number, n = _vint(payload, 0, False)
    if number != track or len(payload) < n + 3:
        return None
    rel = int.from_bytes(payload[n:n + 2], 'big', signed=True)
    return rel, payload[n + 3:]


def matroska_subtitle_events(reader, ordinal, should_stop=None, info=None):
    """The events of the ordinal-th (0 = first) subtitle track of the Matroska file behind reader as
    [(start ms, end ms, raw block text)]; the text of an ASS block is "ReadOrder,Layer,Style,Name,MarginL,
    MarginR,MarginV,Effect,Text". The whole file is walked, but only the headers of the elements: the bulk
    (video, audio) is skipped by seeking. None when the file is no Matroska file, the track is missing, or
    should_stop() says so (called between clusters). When info is a dict, info['header'] gets the track's
    CodecPrivate text (the ASS script header: resolution and styles)."""
    reader = _Buffered(reader)
    top = _header(reader, 0)
    if not top or top[0] != _EBML_HEADER or top[1] < 0:
        return None
    pos = top[2] + top[1]
    seg = _header(reader, pos)
    if not seg or seg[0] != _SEGMENT:
        return None
    pos += seg[2]
    scale = 1000000                      # nanoseconds per tick
    track = None
    events = []
    while True:
        if should_stop and should_stop():
            return None
        el = _header(reader, pos)
        if not el:
            break                        # end of the file
        eid, size, hlen = el
        if size < 0:
            return None
        body = pos + hlen
        if eid == _INFO and size <= _MAX_SEEK_HEAD_BYTES:
            reader.seek(body)
            for cid, payload in _children(reader.read(size)):
                if cid == _TIMESTAMP_SCALE:
                    scale = _uint(payload) or scale
        elif eid == _TRACKS and size <= _MAX_TRACKS_BYTES:
            reader.seek(body)
            tracks = _subtitle_tracks(reader.read(size))
            if ordinal >= len(tracks):
                return None
            track = tracks[ordinal][0]
            if info is not None:
                info['header'] = tracks[ordinal][2].decode('utf-8', 'replace')
                info['codec'] = tracks[ordinal][1]
        elif eid == _CLUSTER:
            if track is None:
                return None
            _cluster_events(reader, body, body + size, track, scale, events)
        pos = body + size
    return events if track is not None else None


def _cluster_events(reader, pos, end, track, scale, events):
    stamp = 0
    to_ms = scale / 1e6
    while pos < end:
        reader.seek(pos)
        window = reader.read(96)
        eid, n1 = _vint(window, 0, True)
        size, n2 = _vint(window, n1, False) if eid is not None else (None, 0)
        if size is None or size < 0:
            return
        body = n1 + n2
        wanted = None                    # (block payload offset in file, block size, duration ticks or None)
        if eid == _CLUSTER_TIMESTAMP:
            stamp = _uint(window[body:body + size])
        elif eid == _SIMPLE_BLOCK:
            number, _n = _vint(window, body, False)
            if number == track:
                wanted = (pos + body, size, None)
        elif eid == _BLOCK_GROUP:
            cid, c1 = _vint(window, body, True)
            csize, c2 = _vint(window, body + c1, False) if cid is not None else (None, 0)
            if cid == _BLOCK and csize is not None:
                number, _n = _vint(window, body + c1 + c2, False)
                if number == track:
                    wanted = (pos + body + c1 + c2, csize, 'group')
                    group = (pos + body, size)
        if wanted:
            start, length, kind = wanted
            reader.seek(start)
            parsed = _block(reader.read(length), track)
            duration = None
            if kind == 'group':
                reader.seek(group[0])
                for cid, payload in _children(reader.read(group[1])):
                    if cid == _BLOCK_DURATION:
                        duration = _uint(payload)
            if parsed:
                rel, data = parsed
                begin = int(round((stamp + rel) * to_ms))
                span = int(round(duration * to_ms)) if duration else _DEFAULT_DURATION_MS
                events.append((begin, begin + span, data.decode('utf-8', 'replace')))
        pos += body + size

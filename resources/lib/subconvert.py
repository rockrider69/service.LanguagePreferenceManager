"""
Sub converter: written to the add-on's own folder and removed again every time the service starts (that is, at every start of Kodi): clean_folder().
"""
import hashlib
import os
import re

import subcodec

FOLDER_NAME = 'converted_subs'
_TOP = 8                                 # numpad alignment (\an8): top centre
_YELLOW = '#FFFF00'

_DRAWING = re.compile(r'\{[^}]*\\p[1-9]')
_OVERRIDES = re.compile(r'\{[^}]*\}')
_MARKUP = re.compile(r'<[^>]*>')
_AN = re.compile(r'\\an([1-9])')
_A_LEGACY = re.compile(r'\\a(\d{1,2})(?!\d)')
_POS = re.compile(r'\\(?:pos|move)\(\s*(-?[\d.]+)\s*,\s*(-?[\d.]+)')


def plain_location(path):
    """A video location without what must not be logged or used in a file name: the headers after '|' (cookies,
    tokens), the query string and user:password@."""
    path = (path or '').split('|', 1)[0].split('?', 1)[0]
    return re.sub(r'^([a-z][a-z0-9+.-]*://)[^/@]*@', r'\1', path, flags=re.I)


def converted_folder(user_data_path):
    return os.path.join(user_data_path, FOLDER_NAME)


def clean_folder(user_data_path, log=None):
    """Delete every converted subtitle: called when the service starts. Returns the number of files removed."""
    folder = converted_folder(user_data_path)
    removed = 0
    if not os.path.isdir(folder):
        return 0
    for name in os.listdir(folder):
        path = os.path.join(folder, name)
        try:
            if os.path.isfile(path):
                os.remove(path)
                removed += 1
        except OSError as e:
            if log:
                log('Sub converter: cannot remove {0}: {1}'.format(path, e))
    return removed


def _legacy_alignment(a):
    """SSA (v4) alignment code -> numpad alignment: 1-3 bottom, 5-7 top (+4), 9-11 middle (+8)."""
    if a in (1, 2, 3):
        return a
    if 5 <= a <= 7:
        return a + 2
    if 9 <= a <= 11:
        return a - 5
    return 2


def parse_header(header):
    """(PlayResX, PlayResY, {style name: numpad alignment}) of an ASS script header."""
    res_x = res_y = None
    styles = {}
    columns = None
    plus = True
    for line in (header or '').splitlines():
        line = line.strip()
        low = line.lower()
        if low.startswith('playresx:'):
            res_x = _number(line.split(':', 1)[1])
        elif low.startswith('playresy:'):
            res_y = _number(line.split(':', 1)[1])
        elif low.startswith('[v4 styles]'):
            plus = False
        elif low.startswith('[v4+ styles]'):
            plus = True
        elif low.startswith('format:') and columns is None:
            columns = [c.strip().lower() for c in line.split(':', 1)[1].split(',')]
        elif low.startswith('style:') and columns and 'alignment' in columns:
            values = [v.strip() for v in line.split(':', 1)[1].split(',')]
            if len(values) >= len(columns):
                try:
                    a = int(values[columns.index('alignment')])
                except ValueError:
                    continue
                styles[values[columns.index('name')]] = a if plus else _legacy_alignment(a)
    return res_x, res_y, styles


def _number(text):
    try:
        return float(text.strip())
    except ValueError:
        return None


def video_view(screen_w, screen_h, aspect):
    """(left, top, width, height) of the picture on the screen: it fills the screen as far as its aspect ratio
    allows (Kodi's normal zoom), centred. ASS coordinates are relative to this picture, the coordinates of a
    {\\pos} in an SRT shown by Kodi are screen pixels."""
    if not (screen_w and screen_h):
        return None
    if not aspect or aspect <= 0:
        return 0.0, 0.0, float(screen_w), float(screen_h)
    if aspect >= float(screen_w) / screen_h:
        width, height = float(screen_w), screen_w / aspect
    else:
        width, height = screen_h * aspect, float(screen_h)
    return (screen_w - width) / 2, (screen_h - height) / 2, width, height


def event_placement(raw, header_info, view=None):
    """(override tag text, positioned) for one Matroska ASS block. A line is positioned when it says where it
    goes: an alignment tag (\\an, \\a), a \\pos / \\move (its start point), or a style that is not bottom centre.
    It then keeps that place: '\\an7\\pos(x,y)' with x, y moved from the script's resolution into the picture on
    the screen (view; its alignment, as ASS does, is the anchor of the point), or just its alignment. Anything
    else is where ASS puts text by default, at the bottom, and is not positioned: it goes to the top."""
    res_x, res_y, styles = header_info
    fields = raw.split(',', 8)
    text = fields[8] if len(fields) == 9 else raw
    tags = ' '.join(_OVERRIDES.findall(text))
    style = styles.get(fields[2], 2) if len(fields) == 9 else 2
    an = None
    m = _AN.search(tags)
    if m:
        an = int(m.group(1))
    else:
        m = _A_LEGACY.search(tags)
        if m:
            an = _legacy_alignment(int(m.group(1)))
    m = _POS.search(tags)
    if m:
        left, top, width, height = view or (0.0, 0.0, 1920.0, 1080.0)
        x = left + float(m.group(1)) * width / (res_x or 384.0)
        y = top + float(m.group(2)) * height / (res_y or 288.0)
        return '\\an{0}\\pos({1},{2})'.format(an or style, int(round(x)), int(round(y))), True
    if an:
        return '\\an{0}'.format(an), True
    if style != 2:
        return '\\an{0}'.format(style), True
    return '\\an{0}'.format(_TOP), False


def ass_text(raw):
    """The plain text lines of one Matroska ASS block ("ReadOrder,Layer,Style,Name,MarginL,MarginR,MarginV,
    Effect,Text"): override tags and drawings gone, \\N / \\n line breaks, \\h a space. [] when nothing is left."""
    fields = raw.split(',', 8)
    text = fields[8] if len(fields) == 9 else raw
    if _DRAWING.search(text):
        return []                                   # vector drawing (a sign), no text
    text = _OVERRIDES.sub('', text)
    text = _MARKUP.sub('', text)
    text = text.replace('\\N', '\n').replace('\\n', '\n').replace('\\h', ' ')
    return [line.strip() for line in text.split('\n') if line.strip()]


_VTT_TAG = re.compile(r'<[^>]*>')


def vtt_cue(raw, codec=''):
    """(lines, placement tag text, positioned) of one Matroska WebVTT block: "settings\\nidentifier\\npayload". A cue
    with a line: setting says where it goes (top half: \\an8, else \\an2, kept); one without goes to the top."""
    parts = raw.replace('\r', '').split('\n', 2)
    if codec.upper().startswith('D_WEBVTT'):         # the block is only the payload (settings are in a side element)
        settings, payload = '', raw
    else:
        settings, payload = (parts[0], parts[2]) if len(parts) == 3 else ('', raw)
    text = _VTT_TAG.sub('', payload).replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')
    text = text.replace('&nbsp;', ' ')
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    m = re.search(r'\bline:(-?[\d.]+)(%?)', settings)
    if m:
        value = float(m.group(1))
        if m.group(2) != '%' and value < 0:
            return lines, '\\an2', True                    # counted from the bottom
        return lines, '\\an{0}'.format(_TOP if value < 50 and m.group(2) == '%' or value == 0 else 2), True
    return lines, '\\an{0}'.format(_TOP), False


_TOP_OF = {1: 7, 2: 8, 3: 9}                         # bottom alignment -> the same column at the top
_AN_FIRST = re.compile(r'\\an([1-9])')
_A_FIRST = re.compile(r'\\a(\d{1,2})(?!\d)')
_POS_FIRST = re.compile(r'\\pos\(\s*(-?[\d.]+)\s*,\s*(-?[\d.]+)\s*\)')
_HAS_MOVE = re.compile(r'\\move\(')
_BOTTOM_FROM = 0.6                                   # a positioned line anchored below this share of the height


def _num(v):
    return ('%g' % v)


def ass_to_top(raw, header_info):
    """The Text field of one Matroska ASS block with a line that sits at the bottom moved to the top. Everything
    else (style, fonts, colours, karaoke, effects, drawings, lines placed elsewhere) is left exactly as it is.
    A bottom line is one whose alignment (\\an / \\a tag, else its style's) is 1-3 and that either has no
    \\pos or has one anchored in the lower part of the picture; a \\pos line is mirrored vertically."""
    res_x, res_y, styles = header_info
    fields = raw.split(',', 8)
    if len(fields) != 9:
        return None
    text = fields[8]
    if _DRAWING.search(text) or _HAS_MOVE.search(text):
        return text                                   # drawings and moving text keep their motion
    style = styles.get(fields[2], 2)
    an = None
    m = _AN_FIRST.search(text)
    if m:
        an = int(m.group(1))
    else:
        m = _A_FIRST.search(text)
        if m:
            an = _legacy_alignment(int(m.group(1)))
    eff = an or style
    if eff not in _TOP_OF:
        return text                                   # already middle or top
    pos = _POS_FIRST.search(text)
    if pos:
        height = res_y or 288.0
        y = float(pos.group(2))
        if y < _BOTTOM_FROM * height:
            return text                               # an anchor in the upper part: a sign, not a bottom line
        text = text[:pos.start()] + '\\pos(%s,%s)' % (pos.group(1), _num(height - y)) + text[pos.end():]
    top = _TOP_OF[eff]
    if _AN_FIRST.search(text):
        return _AN_FIRST.sub(lambda mm: '\\an%d' % top, text, count=1)
    if _A_FIRST.search(text):
        return _A_FIRST.sub(lambda mm: '\\an%d' % top, text, count=1)
    if text.startswith('{'):
        return '{\\an%d' % top + text[1:]           # into the first override block
    return '{\\an%d}' % top + text


def _ass_stamp(ms):
    cs = int(round(max(0, ms) / 10.0))
    return '%d:%02d:%02d.%02d' % (cs // 360000, cs // 6000 % 60, cs // 100 % 60, cs % 100)


_DEFAULT_EVENTS = ('[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n')


def events_to_ass(events, header=''):
    """(text of an .ass file, number of lines) from [(start ms, end ms, raw ASS block text)] and the track's script
    header (CodecPrivate: script info, styles and the [Events] format line). The header, so the styles and the
    fonts they name, is kept as it is; lines at the bottom go to the top (ass_to_top)."""
    info = parse_header(header)
    head = (header or '').replace('\r\n', '\n').replace('\r', '\n').rstrip('\n') + '\n'
    if not re.search(r'^\[Events\]', head, re.M | re.I):
        head += '\n' + _DEFAULT_EVENTS
    elif not re.search(r'^Format:[^\n]*\bText\b', head.split('[Events]')[-1] if '[Events]' in head else '', re.M):
        head = head.rstrip('\n') + '\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n'
    lines = []
    seen = set()
    for start, end, raw in sorted(events, key=lambda e: (e[0], e[1])):
        f = raw.split(',', 8)
        if len(f) != 9:
            continue
        text = ass_to_top(raw, info)
        key = (start, end, f[1], f[2], text)
        if text is None or key in seen:
            continue
        seen.add(key)
        lines.append('Dialogue: %s,%s,%s,%s,%s,%s,%s,%s,%s,%s' % (
            f[1], _ass_stamp(start), _ass_stamp(end), f[2], f[3], f[4], f[5], f[6], f[7], text))
    return head + '\n'.join(lines) + '\n', len(lines)


def _stamp(ms):
    ms = max(0, int(ms))
    return '{0:02d}:{1:02d}:{2:02d},{3:03d}'.format(ms // 3600000, ms // 60000 % 60, ms // 1000 % 60, ms % 1000)


def events_to_srt(events, header='', view=None, codec=''):
    """SRT text of [(start ms, end ms, raw ASS block text)], in time order; every line is yellow. A line the ASS
    file does not position is put at the top of the picture ({\\an8}); a positioned one keeps its place (its
    alignment). Identical lines shown at the same time are written once. header: the track's ASS script header."""
    info = parse_header(header)
    cues = []
    seen = set()
    for start, end, raw in sorted(events, key=lambda e: (e[0], e[1])):
        if subcodec.is_webvtt(codec):
            lines, placement, _positioned = vtt_cue(raw, codec)
        else:
            lines = ass_text(raw)
            placement = None
        key = (start, end, tuple(lines))
        if not lines or key in seen:
            continue
        seen.add(key)
        if placement is None:
            placement, _positioned = event_placement(raw, info, view)
        cues.append((start, end, lines, placement))
    out = []
    for i, (start, end, lines, alignment) in enumerate(cues, 1):
        body = '\n'.join('<font color="{0}">{1}</font>'.format(_YELLOW, line) for line in lines)
        out.append('{0}\n{1} --> {2}\n{{{3}}}{4}\n'.format(i, _stamp(start), _stamp(end), alignment, body))
    return '\n'.join(out), len(cues)


def target_path(user_data_path, video_path, ordinal, language, view=None, ext='srt'):
    """Where the converted copy of subtitle track number ordinal of video_path goes: the video's name, a short
    hash of its full path (two videos with the same name) and the track, then the language code, which is how
    Kodi reads the language of an external subtitle."""
    base = os.path.splitext(os.path.basename(plain_location(video_path).rstrip('/\\')))[0] or 'video'
    base = re.sub(r'[^\w .()\[\]-]', '_', base)[:80]
    tag = hashlib.md5((video_path + repr(view)).encode('utf-8')).hexdigest()[:6]     # a new screen size, a new copy
    lang = re.sub(r'[^A-Za-z-]', '', language or '') or 'und'
    return os.path.join(converted_folder(user_data_path), '{0} [{1}-{2}].{3}.{4}'.format(base, tag, ordinal, lang, ext))


def convert(video_path, ordinal, destination, should_stop=None, log=None, view=None):
    """Write the SRT copy of embedded subtitle track number ordinal of the Matroska file video_path to
    destination (a finished copy there is reused). Returns the number of cues, 0 when nothing was written."""
    if os.path.isfile(destination) and os.path.getsize(destination) > 0:
        return -1                                    # already converted in this Kodi session
    try:
        import xbmcvfs
        handle = xbmcvfs.File(video_path)
    except Exception as e:
        if log:
            log('Sub converter: cannot open {0}: {1}'.format(plain_location(video_path), e))
        return 0
    try:
        info = {}
        events = subcodec.matroska_subtitle_events(subcodec._Reader(handle), ordinal, should_stop, info)
    finally:
        try:
            handle.close()
        except Exception:
            pass
    if not events:
        return 0
    if subcodec.is_ass(info.get('codec', '')) and destination.lower().endswith('.ass'):
        srt, cues = events_to_ass(events, info.get('header', ''))
    else:
        srt, cues = events_to_srt(events, info.get('header', ''), view, info.get('codec', ''))
    if not cues:
        return 0
    os.makedirs(os.path.dirname(destination), exist_ok=True)
    temp = destination + '.part'
    with open(temp, 'w', encoding='utf-8', newline='\n') as f:
        f.write(srt)
    os.replace(temp, destination)
    return cues

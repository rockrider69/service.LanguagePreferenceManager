"""
Kodi's JSON-RPC interface, for what the add-on does with the playing video's streams: which file is playing, loading a
subtitle file, switching subtitles on or off and picking a track, and the screen / picture sizes. The JSON-RPC
methods used (Player.GetActivePlayers, Player.GetItem, Player.AddSubtitle, Player.SetSubtitle, XBMC.GetInfoLabels)
exist in Kodi 19 and newer. Every function returns a plain value and never raises: None / '' / False when Kodi
does not answer or playback stopped meanwhile.
"""
import json

import xbmc


def call(method, params=None):
    """One JSON-RPC request; the reply's 'result', or None when Kodi answers with an error or not at all."""
    query = json.dumps({'jsonrpc': '2.0', 'id': 1, 'method': method, 'params': params or {}})
    try:
        reply = json.loads(xbmc.executeJSONRPC(query))
    except (TypeError, ValueError):
        return None
    if not isinstance(reply, dict) or 'error' in reply:
        return None
    result = reply.get('result')
    return 'OK' if result is None else result


def video_player_id():
    """Id of the active video player (the first active player when there is no video one), None when nothing plays."""
    players = call('Player.GetActivePlayers')
    if not isinstance(players, list) or not players:
        return None
    return next((p.get('playerid') for p in players if p.get('type') == 'video'), players[0].get('playerid'))


def is_playing_video():
    return video_player_id() is not None


def playing_file(player_id=None):
    """Path of the playing item ('' when nothing plays or Kodi does not tell)."""
    if player_id is None:
        player_id = video_player_id()
        if player_id is None:
            return ''
    result = call('Player.GetItem', {'playerid': player_id, 'properties': ['file']})
    item = result.get('item') if isinstance(result, dict) else None
    return (item or {}).get('file') or ''


def add_subtitle(path, player_id=None):
    """Load a subtitle file into the playing video (Kodi selects it). True when Kodi accepted it."""
    if player_id is None:
        player_id = video_player_id()
    if player_id is None:
        return False
    return call('Player.AddSubtitle', {'playerid': player_id, 'subtitle': path}) is not None


def set_subtitle(subtitle, player_id=None):
    """Player.SetSubtitle: 'on', 'off', 'next', 'previous' or a track index. True when Kodi accepted it."""
    if player_id is None:
        player_id = video_player_id()
    if player_id is None:
        return False
    return call('Player.SetSubtitle', {'playerid': player_id, 'subtitle': subtitle}) is not None


def show_subtitles(visible, player_id=None):
    return set_subtitle('on' if visible else 'off', player_id)


def info_labels(labels):
    """{label: text} of Kodi info labels (XBMC.GetInfoLabels); {} when Kodi does not answer."""
    result = call('XBMC.GetInfoLabels', {'labels': list(labels)})
    return result if isinstance(result, dict) else {}

"""
Subtitle color chart for the sub converter: the settings button "Pick a color" runs this (default.py, argument
pick_color). Kodi 21 and newer have a color chart dialog (xbmcgui.Dialog().colorpicker); on an older Kodi a list of
the preset colors is shown instead.
"""
import subconvert


def argb(color):
    """'#RRGGBB' -> 'FFRRGGBB', the form the Kodi color dialog takes."""
    return 'FF' + str(color).lstrip('#')


def from_dialog(text):
    """What the Kodi color dialog returns (AARRGGBB, or RRGGBB, with or without #) -> '#RRGGBB'; None for nothing
    (the dialog was cancelled) or something that is not a color."""
    digits = str(text or '').strip().lstrip('#')
    if len(digits) == 8:
        digits = digits[2:]
    return subconvert.normalize_color(digits)


def choose(dialog, heading, current, preset_labels):
    """Show the color chart (or the list of presets) and return the chosen '#RRGGBB', None when cancelled.
    dialog: an xbmcgui.Dialog; current: '#RRGGBB' selected at the start; preset_labels: names of
    subconvert.COLOR_PRESETS in the same order."""
    picker = getattr(dialog, 'colorpicker', None)
    if picker is not None:
        try:
            return from_dialog(picker(heading, argb(current)))
        except Exception:                      # Kodi without the color dialog
            pass
    index = dialog.select(heading, list(preset_labels))
    if 0 <= index < len(subconvert.COLOR_PRESETS):
        return subconvert.COLOR_PRESETS[index]
    return None


def store(addon, color):
    """Keep the chosen color in the settings: the 'Custom' entry of the color spinner plus its hex field. A preset
    color is stored as that preset."""
    if color in subconvert.COLOR_PRESETS:
        addon.setSetting('subConverterColor', str(subconvert.COLOR_PRESETS.index(color)))
    else:
        addon.setSetting('subConverterColorHex', color.lstrip('#'))
        addon.setSetting('subConverterColor', str(len(subconvert.COLOR_PRESETS)))

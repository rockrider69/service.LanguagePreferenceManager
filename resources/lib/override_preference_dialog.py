import xbmcgui
import xbmcaddon

from logger import *
from custom_media_preference import media_preference_manager

window_control_id = 100


class OverridePreferenceDialog(xbmcgui.WindowXMLDialog):
    def __init__(self, *args, **kwargs):
        xbmcgui.WindowXMLDialog.__init__(self, *args, **kwargs)
        self.list_control = None
        self.preference_list = None

    def onInit(self):
        self.list_control = self.getControl(window_control_id)
        self.preference_list = []
        self.fill_preference_list()
        self.setFocusId(window_control_id)

    def fill_preference_list(self):
        """
        Fill the list control with all preferences from the media preference manager.
        This will create a list item for each preference and add it to the list control.
        :return: None
        """
        items = self.get_all_preferences()
        for preference in items:
            label_name = preference.selector.to_string()
            log(LOG_DEBUG, f"Adding item: {label_name}")
            li = xbmcgui.ListItem(label=label_name)
            self.list_control.addItem(li)

            # We want to track the items by index, so we can get them later on
            # (the media preference list could have been changed, we don't want to alter the wrong item)
            self.preference_list.append(preference)

    def get_preference_by_index(self, index):
        """
        Get a preference by index from the media preference manager.
        :param index: The index of the preference to get.
        :return:
        """
        if index < 0 or index >= len(self.preference_list):
            return None
        return self.preference_list[index]

    def get_all_preferences(self):
        """
        Get all preferences from the media preference manager.

        :return: A cloned list of all preferences (CustomMediaPreference) from the media preference manager.
        """
        item_list = []
        for preference in media_preference_manager.preferences:
            item_list.append(preference)

        return item_list

    def onClick(self, controlId):
        """
        Handle the click event for the list control.
        This will remove the selected item from the list and the media preference manager, if the user confirms.
        :param controlId: The control ID of the clicked control.
        :return: None
        """
        if controlId == window_control_id:
            selected_item = self.list_control.getSelectedItem()
            # Ask for delete confirmation
            if selected_item:
                result = xbmcgui.Dialog().yesno("Delete Confirmation",
                                                f"Do you want to delete {selected_item.getLabel()}?")
                if result:
                    preference = self.get_preference_by_index(self.list_control.getSelectedPosition())

                    if preference:
                        # Remove the preference from the media preference manager
                        media_preference_manager.remove_preference(preference)
                        media_preference_manager.save_preferences()

                        log(LOG_INFO, f"Removing preference: {preference}")

                        # Remove the item from the list
                        self.list_control.removeItem(self.list_control.getSelectedPosition())


dialog = OverridePreferenceDialog("override_preference_dialog.xml", xbmcaddon.Addon().getAddonInfo('path'), "default",
                                  "1080i")
dialog.doModal()
del dialog

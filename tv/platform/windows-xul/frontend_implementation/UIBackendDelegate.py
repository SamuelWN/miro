# Miro - an RSS based video player application
# Copyright (C) 2005-2007 Participatory Culture Foundation
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA  02110-1301 USA

import os
import logging
import subprocess
import resources
import webbrowser
import _winreg
import traceback
import ctypes
from gtcache import gettext as _
from urlparse import urlparse

import prefs
import config
import dialogs
import feed
import frontend
import clipboard
import util

currentId = 1
def nextDialogId():
    global currentId
    rv = currentId
    currentId += 1
    return rv

def getPrefillText(dialog):
    if dialog.fillWithClipboardURL:
        text = clipboard.getText()
        if text is not None:
            text = feed.normalizeFeedURL(text)
            if text is not None and feed.validateFeedURL(text):
                return text
    if dialog.prefillCallback:
        text = dialog.prefillCallback()
        if text is not None:
            return text
    return ''

def _makeSupportsArrayFromSecondElement(data):
    from xpcom import components
    arrayAbs = components.classes["@mozilla.org/supports-array;1"].createInstance();
    array = arrayAbs.queryInterface(components.interfaces.nsISupportsArray)
    for datum in data:
        supportsStringAbs = components.classes["@mozilla.org/supports-string;1"].createInstance();
        supportsString = supportsStringAbs.queryInterface(components.interfaces.nsISupportsString)
        supportsString.data = datum[1]
        array.AppendElement(supportsString)
    return array

class UpdateAvailableDialog(dialogs.Dialog):
    """Give the user a choice of 2 options (Yes/No, Ok/Cancel,
    Migrate/Don't Migrate, etc.)
    """

    def __init__(self, releaseNotes):
        title = _("Update Available")
        description = _("A new version of %s is available for download.") % (config.get(prefs.LONG_APP_NAME))
        self.releaseNotes = releaseNotes
        super(UpdateAvailableDialog, self).__init__(title, description,
                [dialogs.BUTTON_DOWNLOAD, dialogs.BUTTON_NOT_NOW])


class UIBackendDelegate:
    openDialogs = {}
    currentMenuItems = None

    def performStartupTasks(self, terminationCallback):
        terminationCallback(None)

    def showContextMenu(self, menuItems):
        UIBackendDelegate.currentMenuItems = menuItems
        def getLabelString(menuItem):
            if menuItem.callback is not None or menuItem.label == '':
                return menuItem.label
            else:
                # hack to tell xul code that this item is disabled
                return "_" + menuItem.label 
        menuString = '\n'.join([getLabelString(m) for m in menuItems])
        frontend.jsBridge.showContextMenu(menuString)

    def runDialog(self, dialog):
        id = nextDialogId()
        self.openDialogs[id] = dialog
        if isinstance(dialog, dialogs.ChoiceDialog):
            frontend.jsBridge.showChoiceDialog(id, dialog.title,
                    dialog.description, dialog.buttons[0].text,
                    dialog.buttons[1].text)
        elif isinstance(dialog, dialogs.CheckboxTextboxDialog):
            frontend.jsBridge.showCheckboxTextboxDialog(id, dialog.title,
                    dialog.description, dialog.buttons[0].text,
                    dialog.buttons[1].text, dialog.checkbox_text, 
                    dialog.checkbox_value, dialog.textbox_value)
        elif isinstance(dialog, dialogs.CheckboxDialog):
            frontend.jsBridge.showCheckboxDialog(id, dialog.title,
                    dialog.description, dialog.buttons[0].text,
                    dialog.buttons[1].text, dialog.checkbox_text, 
                    dialog.checkbox_value)
        elif isinstance(dialog, dialogs.ThreeChoiceDialog):
            frontend.jsBridge.showThreeChoiceDialog(id, dialog.title,
                    dialog.description, dialog.buttons[0].text,
                    dialog.buttons[1].text, dialog.buttons[2].text)
        elif isinstance(dialog, dialogs.MessageBoxDialog):
            frontend.jsBridge.showMessageBoxDialog(id, dialog.title,
                    dialog.description)
        elif isinstance(dialog, dialogs.HTTPAuthDialog):
            frontend.jsBridge.showHTTPAuthDialog(id, dialog.description)
        elif isinstance(dialog, dialogs.TextEntryDialog):
            frontend.jsBridge.showTextEntryDialog(id, dialog.title,
                    dialog.description, dialog.buttons[0].text,
                    dialog.buttons[1].text, getPrefillText(dialog))
        elif isinstance(dialog, UpdateAvailableDialog):
            frontend.jsBridge.showUpdateAvailableDialog(id, dialog.title,
                    dialog.description, dialog.buttons[0].text,
                    dialog.buttons[1].text, dialog.releaseNotes)
        elif isinstance(dialog, dialogs.SearchChannelDialog):
            engines = _makeSupportsArrayFromSecondElement(dialog.engines)
            channels = _makeSupportsArrayFromSecondElement(dialog.channels)
            defaultTerm = ""
            if len(dialog.channels) > 0:
                defaultChannelId = dialog.channels[0][0]
            else:
                defaultChannelId = 0
            defaultEngineName = dialog.defaultEngine
            defaultURL = ""
            if dialog.term:
                defaultTerm = dialog.term
            if dialog.style == dialog.CHANNEL:
                if dialog.location is not None:
                    defaultChannelId = dialog.location
            elif dialog.style == dialog.ENGINE:
                if dialog.location is not None:
                    defaultEngineName = dialog.location
            elif dialog.style == dialog.URL:
                if dialog.location is not None:
                    defaultURL = dialog.location
            defaultChannel = 0
            defaultEngine = 0
            for i in xrange (len (dialog.channels)):
                if dialog.channels[i][0] == defaultChannelId:
                    defaultChannel = i
                    break
            for i in xrange (len (dialog.engines)):
                if dialog.engines[i][0] == defaultEngineName:
                    defaultEngine = i
                    break
            frontend.jsBridge.showSearchChannelDialog(id, channels, engines, defaultTerm, dialog.style, defaultChannel, defaultEngine, defaultURL)
        else:
            del self.openDialogs[id]
            dialog.runCallback(None)

    def askForOpenPathname(self, title, callback, defaultDirectory=None, 
            typeString=None, types=None):
        id = nextDialogId()
        self.openDialogs[id] = callback
        frontend.jsBridge.showOpenDialog(id, title, defaultDirectory,
                typeString, types)

    def askForSavePathname(self, title, callback, defaultDirectory=None, 
            defaultFilename=None):
        id = nextDialogId()
        self.openDialogs[id] = callback
        frontend.jsBridge.showSaveDialog(id, title, defaultDirectory,
                defaultFilename)

    def handleFileDialog(self, dialogID, pathname):
        try:
            callback = self.openDialogs.pop(dialogID)
        except KeyError:
            return
        util.trapCall('File dialog callback', callback, pathname)

    def handleContextMenu(self, index):
        self.currentMenuItems[index].activate()

    def handleDialog(self, dialogID, buttonIndex, *args, **kwargs):
        try:
            dialog = self.openDialogs.pop(dialogID)
        except KeyError:
            return
        if buttonIndex is not None:
            choice = dialog.buttons[buttonIndex]
        else:
            choice = None
        if isinstance (dialog, dialogs.SearchChannelDialog):
            dialog.term = kwargs['term']
            dialog.style = kwargs['style']
            if choice == dialogs.BUTTON_CREATE_CHANNEL:
                try:
                    if dialog.style == dialog.CHANNEL:
                        dialog.location = dialog.channels[int(kwargs['loc'])][0]
                    elif dialog.style == dialog.ENGINE:
                        dialog.location = dialog.engines[int(kwargs['loc'])][0]
                    elif dialog.style == dialog.URL:
                        dialog.location = kwargs['loc']
                except:
                    choice = dialogs.BUTTON_CANCEL
            kwargs = {}
        dialog.runCallback(choice, *args, **kwargs)

    def openExternalURL(self, url):
        # It looks like the maximum URL length is about 2k. I can't
        # seem to find the exact value
        if len(url) > 2047:
            url = url[:2047]
        try:
            webbrowser.get("windows-default").open_new(url)
        except:
            print "WARNING: Error opening URL: %r" % url
            traceback.print_exc()
            recommendURL = config.get(prefs.RECOMMEND_URL)

            if url.startswith(config.get(prefs.VIDEOBOMB_URL)):
                title = _('Error Bombing Item')
            elif url.startswith(recommendURL):
                title = _('Error Recommending Item')
            else:
                title = _("Error Opening Website")

            scheme, host, path, params, query, fragment = urlparse(url)
            shortURL = '%s:%s%s' % (scheme, host, path)
            msg = _("There was an error opening %s.  Please try again in "
                    "a few seconds") % shortURL
            dialogs.MessageBoxDialog(title, msg).run()

    def revealFile (self, filename):
        os.startfile(os.path.dirname(filename))

    def notifyDownloadCompleted(self, item):
        pass

    def notifyDownloadFailed(self, item):
        pass

    def updateAvailableItemsCountFeedback(self, count):
        # Inform the user in a way or another that newly available items are
        # available
        # FIXME: When we have a system tray icon, remove that
        pass

    def notifyUnkownErrorOccurence(self, when, log = ''):
        if config.get(prefs.SHOW_ERROR_DIALOG):
            frontend.jsBridge.showBugReportDialog(when, log)

    def copyTextToClipboard(self, text):
        frontend.jsBridge.copyTextToClipboard(text)

    # This is windows specific right now. We don't need it on other platforms
    def setRunAtStartup(self, value):
        runSubkey = "Software\\Microsoft\\Windows\\CurrentVersion\\Run"
        try:
            folder = _winreg.OpenKey(_winreg.HKEY_CURRENT_USER, runSubkey, 0,
                    _winreg.KEY_SET_VALUE)
        except WindowsError, e:
            if e.errno == 2: # registry key doesn't exist
                folder = _winreg.CreateKey(_winreg.HKEY_CURRENT_USER,
                        runSubkey)
            else:
                raise
        if (value):
            filename = os.path.join(resources.resourceRoot(),"..",("%s.exe" % config.get(prefs.SHORT_APP_NAME)))
            filename = os.path.normpath(filename)
            _winreg.SetValueEx(folder, config.get(prefs.LONG_APP_NAME), 0,_winreg.REG_SZ, filename)
        else:
            try:
                _winreg.DeleteValue(folder, config.get(prefs.LONG_APP_NAME))
            except WindowsError, e:
                if e.errno == 2: 
                    # registry key doesn't exist, user must have deleted it
                    # manual
                    pass
                else:
                    raise

    def killProcess(self, pid):
        # Kill the old process, if it exists
        if pid is not None:
            # This isn't guaranteed to kill the process, but it's likely the
            # best we can do
            # See http://support.microsoft.com/kb/q178893/
            # http://aspn.activestate.com/ASPN/Cookbook/Python/Recipe/347462
            PROCESS_TERMINATE = 1
            handle = ctypes.windll.kernel32.OpenProcess(PROCESS_TERMINATE, False, pid)
            ctypes.windll.kernel32.TerminateProcess(handle, -1)
            ctypes.windll.kernel32.CloseHandle(handle)

    def launchDownloadDaemon(self, oldpid, env):
        self.killProcess(oldpid)
        for key, value in env.items():
            os.environ[key] = value
        os.environ['DEMOCRACY_DOWNLOADER_LOG'] = \
                config.get(prefs.DOWNLOADER_LOG_PATHNAME)
        # Start the downloader.  We use the subprocess module to turn off the
        # console.  One slightly awkward thing is that the current process
        # might not have a valid stdin/stdout/stderr, so we create a pipe to
        # it that we never actually use.
        downloaderPath = os.path.join(resources.resourceRoot(), "..",
                ("%s_Downloader.exe" % config.get(prefs.SHORT_APP_NAME)))
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        subprocess.Popen(downloaderPath, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, 
                stdin=subprocess.PIPE,
                startupinfo=startupinfo)

    def handleNewUpdate(self, update_item):
        url = update_item['enclosures'][0]['href']
        try:
            releaseNotes = update_item['description']
        except:
            logging.warn("Couldn't fetch release notes")
            releaseNotes = ''
        dialog = UpdateAvailableDialog(releaseNotes)
        def callback(dialog):
            if dialog.choice == dialogs.BUTTON_DOWNLOAD:
                self.openExternalURL(url)
        dialog.run(callback)

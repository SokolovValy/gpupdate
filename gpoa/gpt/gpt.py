import logging
import os

from samba.gp_parse.gp_pol import GPPolParser

from storage import registry_factory
from .shortcuts import read_shortcuts
import util
import util.preg

global __default_policy_path

__default_policy_path = '/usr/share/local-policy/default'

class gpt:
    __default_policy_path = '/usr/share/local-policy/default'
    __user_policy_mode_key = 'Software\\Policies\\Microsoft\\Windows\\System\\UserPolicyMode'

    def __init__(self, gpt_path, sid=None):
        self.path = gpt_path
        self.sid = sid
        self.storage = registry_factory('registry')
        self._scan_gpt()

    def _scan_gpt(self):
        '''
        Collect the data from the specified GPT on file system (cached
        by Samba).
        '''
        self.guid = self.path.rpartition('/')[2]
        self.name = ''
        if 'default' == self.guid:
            self.guid = 'Local Policy'

        self._machine_path = None
        self._user_path = None
        self._get_machine_user_dirs()

        logging.debug('Looking for machine part of GPT {}'.format(self.guid))
        self._find_machine()
        logging.debug('Looking for user part of GPT {}'.format(self.guid))
        self._find_user()

        self._user_policy_mode = self.get_policy_mode()

    def set_name(self, name):
        '''
        Set human-readable GPT name.
        '''
        self.name = name

    def get_policy_mode(self):
        '''
        Get UserPolicyMode parameter value in order to determine if it
        is possible to work with user's part of GPT
        '''
        upm = 0
        if self._machine_regpol:
            keymap = util.preg.preg_keymap(self._machine_regpol)
            upm = keymap.get(self.__user_policy_mode_key, 0)

        return upm

    def _get_machine_user_dirs(self):
        '''
        Find full path to Machine and User parts of GPT.
        '''
        entries = os.listdir(self.path)
        for entry in entries:
            full_entry_path = os.path.join(self.path, entry)
            if os.path.isdir(full_entry_path):
                if 'machine' == entry.lower():
                    self._machine_path = full_entry_path
                if 'user' == entry.lower():
                    self._user_path = full_entry_path

    def _find_user(self):
        self._user_regpol = self._find_regpol('user')
        self._user_shortcuts = self._find_shortcuts('user')

    def _find_machine(self):
        self._machine_regpol = self._find_regpol('machine')
        self._machine_shortcuts = self._find_shortcuts('machine')

    def _find_regpol(self, part):
        '''
        Find Registry.pol files.
        '''
        search_path = self._machine_path
        if 'user' == part:
            search_path = self._user_path
        if not search_path:
            return None

        return find_file(search_path, 'registry.pol')

    def _find_shortcuts(self, part):
        '''
        Find Shortcuts.xml files.
        '''
        search_path = os.path.join(self._machine_path, 'Preferences', 'Shortcuts')
        if 'user' == part:
            search_path = os.path.join(self._user_path, 'Preferences', 'Shortcuts')
        if not search_path:
            return None

        return find_file(search_path, 'shortcuts.xml')

    def _merge_shortcut(self, sid, sc):
        self.storage.add_shortcut(sid, sc)

    def merge(self, sid=None):
        '''
        Merge machine and user (if sid provided) settings to storage.
        '''
        # Merge machine settings to registry if possible
        if self._machine_regpol:
            logging.debug('Merging machine settings from {}'.format(self._machine_regpol))
            util.preg.merge_polfile(self._machine_regpol)

        # Merge user settings if UserPolicyMode set accordingly
        # and user settings (for HKCU) are exist.
        if sid:
            if self._user_policy_mode in [None, '0', '1']:
                if self._user_regpol:
                    logging.debug('Merging user settings from {} for {}'.format(self._user_regpol, sid))
                    util.preg.merge_polfile(self._user_regpol, sid)
            if self._machine_shortcuts:
                logging.debug('Merging user settings for shortcuts')
                for link in self._user_shortcuts:
                    self._merge_shortcut(sid, link)

    def __str__(self):
        template = '''
GUID: {}
Name: {}
For SID: {}

Machine part: {}
Machine Registry.pol: {}
Machine Shortcuts.xml: {}

User part: {}
User Registry.pol: {}
User Shortcuts.xml: {}

UserPolicyMode: {}

'''
        result = template.format(
            self.guid,
            self.name,
            self.sid,

            self._machine_path,
            self._machine_regpol,
            self._machine_shortcuts,

            self._user_path,
            self._user_regpol,
            self._user_shortcuts,

            self._user_policy_mode
        )
        return result

def find_file(search_path, name):
    '''
    Attempt for case-insensitive file search in directory.
    '''
    try:
        file_list = os.listdir(search_path)
        for entry in file_list:
            file_path = os.path.join(search_path, entry)
            if os.path.isfile(file_path) and name.lower() == entry.lower():
                return file_path
    except Exception as exc:
        logging.error(exc)

    return None

def lp2gpt():
    '''
    Convert local-policy to full-featured GPT.
    '''
    lppath = os.path.join(__default_policy_path, 'local.xml')
    machinesettings = os.path.join(__default_policy_path, 'Machine')

    # Load settings from XML PolFile
    polparser = GPPolParser()
    polfile = util.preg.load_preg(lppath)
    polparser.pol_file = polfile

    # Write PReg
    os.makedirs(machinesettings, exist_ok=True)
    polparser.write_binary(os.path.join(machinesettings, 'Registry.pol'))

def get_local_gpt(sid):
    '''
    Convert default policy to GPT and create object out of it.
    '''
    lp2gpt()
    local_policy = gpt(__default_policy_path, sid)
    local_policy.set_name('Local Policy')

    return local_policy
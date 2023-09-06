#
# GPOA - GPO Applier for Linux
#
# Copyright (C) 2019-2023 BaseALT Ltd.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

from .applier_frontend import applier_frontend, check_enabled
from util.logging import log
from util.util import get_homedir

import os
import subprocess
import json

widget_utilities = {
            'colorscheme': 'plasma-apply-colorscheme',
            'cursortheme': 'plasma-apply-cursortheme',
            'desktoptheme': 'plasma-apply-desktoptheme',
            'wallpaperimage': 'plasma-apply-wallpaperimage'
        }

class kde_applier(applier_frontend):
    __module_name = 'KdeApplier'
    __module_experimental = True
    __module_enabled = False
    __hklm_branch = 'Software\\BaseALT\\Policies\\KDE\\'
    __hklm_lock_branch = 'Software\\BaseALT\\Policies\\KDELocks\\'

    def __init__(self, storage):
        self.storage = storage
        self.locks_dict = {}
        self.locks_data_dict = {}
        self.all_kde_settings = {}
        kde_filter = '{}%'.format(self.__hklm_branch)
        locks_filter = '{}%'.format(self.__hklm_lock_branch)
        self.locks_settings = self.storage.filter_hklm_entries(locks_filter)
        self.kde_settings = self.storage.filter_hklm_entries(kde_filter)
        self.all_kde_settings = {}

        self.__module_enabled = check_enabled(
            self.storage,
            self.__module_name,
            self.__module_experimental
        )

    def apply(self):
        if self.__module_enabled:
            log('D198')
            create_dict(self.kde_settings, self.all_kde_settings, self.locks_settings, self.locks_dict)
            apply(self.all_kde_settings, self.locks_dict)
        else:
            log('D199')

class kde_applier_user(applier_frontend):
    __module_name = 'KdeApplierUser'
    __module_experimental = True
    __module_enabled = False
    __hkcu_branch = 'Software\\BaseALT\\Policies\\KDE\\'
    __hkcu_lock_branch = 'Software\\BaseALT\\Policies\\KDELocks\\'
    widget_utilities = {
            'colorscheme': 'plasma-apply-colorscheme',
            'cursortheme': 'plasma-apply-cursortheme',
            'desktoptheme': 'plasma-apply-desktoptheme',
            'wallpaperimage': 'plasma-apply-wallpaperimage'
        }

    def __init__(self, storage, sid=None, username=None):
        self.storage = storage
        self.username = username
        self.sid = sid
        self.locks_dict = {}
        self.locks_data_dict = {}
        self.all_kde_settings = {}
        kde_filter = '{}%'.format(self.__hkcu_branch)
        locks_filter = '{}%'.format(self.__hkcu_lock_branch)
        self.locks_settings = self.storage.filter_hkcu_entries(self.sid, locks_filter)
        self.kde_settings = self.storage.filter_hkcu_entries(self.sid, kde_filter)
        self.__module_enabled = check_enabled(
            self.storage,
            self.__module_name,
            self.__module_experimental
        )

    def admin_context_apply(self):
        pass

    def user_context_apply(self):
        '''
        Change settings applied in user context
        '''
        if self.__module_enabled:
            log('D200')
            create_dict(self.kde_settings, self.all_kde_settings, self.locks_settings, self.locks_dict, self.username)
            apply(self.all_kde_settings, self.locks_dict, self.username)
        else:
            log('D201')

def create_dict(kde_settings, all_kde_settings, locks_settings, locks_dict, username = None):
        for locks in locks_settings:
            locks_dict[locks.valuename] = locks.data
        for setting in kde_settings:
            try:
                file_name, section, value = setting.keyname.split("\\")[-2], setting.keyname.split("\\")[-1], setting.valuename
                data = setting.data
                if file_name == 'plasma':
                    apply_for_widget(section, data)
                if file_name not in all_kde_settings:
                    all_kde_settings[file_name] = {}
                if section not in all_kde_settings[file_name]:
                    all_kde_settings[file_name][section] = {}
                all_kde_settings[file_name][section][value] = data

            except Exception as exc:
                logdata = dict()
                logdata['Exception'] = exc
                logdata['Exception'] = setting
                log('W16', logdata)

def apply(all_kde_settings, locks_dict, username = None):
    if username is None:
        for file_name, sections in all_kde_settings.items():
            file_path = f'/etc/xdg/{file_name}'
            if os.path.exists(file_path):
                os.remove(file_path)
            with open(file_path, 'w') as file:
                for section, keys in sections.items():
                    file.write(f'[{section}]\n')
                    for key, value in keys.items():
                        if key in locks_dict and locks_dict[key] == '1':
                            file.write(f'{key}[$i]={value}\n')
                        else:
                            file.write(f'{key}={value}\n')
                    file.write('\n')
    else:
        for file_name, sections in all_kde_settings.items():
            for section, keys in sections.items():
                for key, value in keys.items():
                    if key in locks_dict and locks_dict[key] == '1':
                        command = [
                            'kwriteconfig5',
                            '--file', file_name,
                            '--group', section,
                            '--key', key +'/$i/',
                            '--type', 'string',
                            value
                        ]
                    else:
                        command = [
                            'kwriteconfig5',
                            '--file', file_name,
                            '--group', section,
                            '--key', key,
                            '--type', 'string',
                            value
                        ]
                    try:
                        subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                    except Exception as exc:
                        clear_locks_settings(username, file_name, key)
                        try:
                            subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE) 
                        except Exception as exc:
                            logdata = dict()
                            logdata['command'] = command
                            log('E68', logdata)
            new_content = []
            file_path = os.path.expanduser(f'{get_homedir(username)}/.config/{file_name}')
            with open(file_path, 'r') as file:
                for line in file:
                    line = line.replace('/$i/', '[$i]').replace(')(', '][')
                    new_content.append(line)
            with open(file_path, 'w') as file:
                file.writelines(new_content)
            logdata = dict()
            logdata['file'] = file_name
            log('D202', logdata)

def clear_locks_settings(username, file_name, key):
    '''
    Method to remove old locked settings
    '''
    file_path = f'{get_homedir(username)}/.config/{file_name}'
    with open(file_path, 'r') as file:
        lines = file.readlines()
    with open(file_path, 'w') as file:
        for line in lines:
            if f'{key}[$i]=' not in line:
                file.write(line)
    for line in lines:
        if f'{key}[$i]=' in line:
            logdata = dict()
            logdata['line'] = line.strip() 
            log('I10', logdata)

def apply_for_widget(value, data):
    '''
    Method for changing graphics settings in plasma context
    '''
    try:
            if value in widget_utilities:
                os.environ["PATH"] = "/usr/lib/kf5/bin:"
                command = [f"{widget_utilities[value]}", f"{data}"]
                proc = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                if proc.returncode == None:
                    log('D203')
                else:
                    log('E66')
            else:
                pass
    except OSError as e:
        log('E67')
#
# GPOA - GPO Applier for Linux
#
# Copyright (C) 2019-2021 BaseALT Ltd.
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

import logging
import os
import pwd
import subprocess

from gi.repository import (
      Gio
    , GLib
)

from .applier_frontend import (
      applier_frontend
    , check_enabled
    , check_windows_mapping_enabled
)
from .appliers.gsettings import (
    system_gsettings,
    user_gsetting
)
from util.logging import slogm

def uri_fetch(schema, path, value, cache):
    '''
    Function to fetch and cache uri
    '''
    retval = value
    logdata = dict()
    logdata['schema'] = schema
    logdata['path'] = path
    logdata['src'] = value
    try:
        retval = cache.get(value)
        logdata['dst'] = retval
        logging.debug(slogm('Getting cached file for URI: {}'.format(logdata)))
    except Exception as exc:
        pass

    return retval

class gsettings_applier(applier_frontend):
    __module_name = 'GSettingsApplier'
    __module_experimental = False
    __module_enabled = True
    __registry_branch = 'Software\\BaseALT\\Policies\\GSettings\\'
    __registry_locks_branch = 'Software\\BaseALT\\Policies\\GSettingsLocks\\'
    __wallpaper_entry = 'Software\\BaseALT\\Policies\\GSettings\\org.mate.background.picture-filename'
    __global_schema = '/usr/share/glib-2.0/schemas'
    __override_priority_file = 'zzz_policy.gschema.override'
    __override_old_file = '0_policy.gschema.override'
    __windows_settings = dict()

    def __init__(self, storage, file_cache):
        self.storage = storage
        self.file_cache = file_cache
        gsettings_filter = '{}%'.format(self.__registry_branch)
        gsettings_locks_filter = '{}%'.format(self.__registry_locks_branch)
        self.gsettings_keys = self.storage.filter_hklm_entries(gsettings_filter)
        self.gsettings_locks = self.storage.filter_hklm_entries(gsettings_locks_filter)
        self.override_file = os.path.join(self.__global_schema, self.__override_priority_file)
        self.override_old_file = os.path.join(self.__global_schema, self.__override_old_file)
        self.gsettings = system_gsettings(self.override_file)
        self.locks = dict()
        self.dictArr = dict()
        self.__module_enabled = check_enabled(
              self.storage
            , self.__module_name
            , self.__module_experimental
        )

    def update_file_cache(self, data):
        try:
            self.file_cache.store(data)
        except Exception as exc:
            logdata = dict()
            logdata['exception'] = str(exc)
            logging.debug(slogm('Unable to cache specified URI for machine: {}'.format(logdata)))

    def uri_fetch_helper(self, schema, path, value):
        return uri_fetch(schema, path, value, self.file_cache)

    def run(self):
        # Compatility cleanup of old settings
        if os.path.exists(self.override_old_file):
            os.remove(self.override_old_file)

        # Cleanup settings from previous run
        if os.path.exists(self.override_file):
            logging.debug(slogm('Removing GSettings policy file from previous run'))
            os.remove(self.override_file)

        # Get all configured gsettings locks
        for lock in self.gsettings_locks:
            valuename = lock.hive_key.rpartition('\\')[2]
            self.locks[valuename] = int(lock.data)

        # Calculate all configured gsettings
        for setting in self.gsettings_keys:
            helper = None
            valuename = setting.hive_key.rpartition('\\')[2]
            rp = valuename.rpartition('.')
            schema = rp[0]
            path = rp[2]
            lock = bool(self.locks[valuename]) if valuename in self.locks else None
            if setting.hive_key.lower() == self.__wallpaper_entry.lower():
                self.update_file_cache(setting.data)
                helper = self.uri_fetch_helper

            if valuename == setting.data:
                valuenameArr = setting.keyname.rpartition('\\')[2]
                rpArr = valuenameArr.rpartition('.')
                schema = rpArr[0]
                path = rpArr[2]
                if self.dictArr and path in self.dictArr.keys():
                    self.dictArr[path].append(setting.data)
                    self.gsettings.pop()
                else:
                    self.dictArr[path] = [setting.data,]
                lock = bool(self.locks[valuenameArr]) if valuenameArr in self.locks else None
                self.gsettings.append(schema, path, self.dictArr[path], lock, helper)
                continue
            self.gsettings.append(schema, path, setting.data, lock, helper)
        # Create GSettings policy with highest available priority
        self.gsettings.apply()

        # Recompile GSettings schemas with overrides
        try:
            proc = subprocess.run(args=['/usr/bin/glib-compile-schemas', self.__global_schema], capture_output=True, check=True)
        except Exception as exc:
            logging.debug(slogm('Error recompiling global GSettings schemas'))

        # Update desktop configuration system backend
        try:
            proc = subprocess.run(args=['/usr/bin/dconf', "update"], capture_output=True, check=True)
        except Exception as exc:
            logging.debug(slogm('Error update desktop configuration system backend'))

    def apply(self):
        if self.__module_enabled:
            logging.debug(slogm('Running GSettings applier for machine'))
            self.run()
        else:
            logging.debug(slogm('GSettings applier for machine will not be started'))

class GSettingsMapping:
    def __init__(self, hive_key, gsettings_schema, gsettings_key):
        self.hive_key = hive_key
        self.gsettings_schema = gsettings_schema
        self.gsettings_key = gsettings_key

        try:
            self.schema_source = Gio.SettingsSchemaSource.get_default()
            self.schema = self.schema_source.lookup(self.gsettings_schema, True)
            self.gsettings_schema_key = self.schema.get_key(self.gsettings_key)
            self.gsettings_type = self.gsettings_schema_key.get_value_type()
        except Exception as exc:
            logdata = dict()
            logdata['hive_key'] = self.hive_key
            logdata['gsettings_schema'] = self.gsettings_schema
            logdata['gsettings_key'] = self.gsettings_key
            logging.warning(slogm('Unable to resolve GSettings parameter {}.{}'.format(self.gsettings_schema, self.gsettings_key)))

    def preg2gsettings(self):
        '''
        Transform PReg key variant into GLib.Variant. This function
        performs mapping of PReg type system into GLib type system.
        '''
        pass

    def gsettings2preg(self):
        '''
        Transform GLib.Variant key type into PReg key type.
        '''
        pass

class gsettings_applier_user(applier_frontend):
    __module_name = 'GSettingsApplierUser'
    __module_experimental = False
    __module_enabled = True
    __registry_branch = 'Software\\BaseALT\\Policies\\GSettings\\'
    __wallpaper_entry = 'Software\\BaseALT\\Policies\\GSettings\\org.mate.background.picture-filename'

    def __init__(self, storage, file_cache, sid, username):
        self.storage = storage
        self.file_cache = file_cache
        self.sid = sid
        self.username = username
        gsettings_filter = '{}%'.format(self.__registry_branch)
        self.gsettings_keys = self.storage.filter_hkcu_entries(self.sid, gsettings_filter)
        self.gsettings = list()
        self.__module_enabled = check_enabled(self.storage, self.__module_name, self.__module_enabled)
        self.__windows_mapping_enabled = check_windows_mapping_enabled(self.storage)
        self.dictArr = dict()
        self.__windows_settings = dict()
        self.windows_settings = list()
        mapping = [
              # Disable or enable screen saver
              GSettingsMapping(
                  'Software\\Policies\\Microsoft\\Windows\\Control Panel\\Desktop\\ScreenSaveActive'
                , 'org.mate.screensaver'
                , 'idle-activation-enabled'
              )
              # Timeout in seconds for screen saver activation. The value of zero effectively disables screensaver start
            , GSettingsMapping(
                  'Software\\Policies\\Microsoft\\Windows\\Control Panel\\Desktop\\ScreenSaveTimeOut'
                , 'org.mate.session'
                , 'idle-delay'
              )
              # Enable or disable password protection for screen saver
            , GSettingsMapping(
                  'Software\\Policies\\Microsoft\\Windows\\Control Panel\\Desktop\\ScreenSaverIsSecure'
                , 'org.mate.screensaver'
                , 'lock-enabled'
              )
              # Specify image which will be used as a wallpaper
            , GSettingsMapping(
                  'Software\\Microsoft\\Windows\\CurrentVersion\\Policies\\System\\Wallpaper'
                , 'org.mate.background'
                , 'picture-filename'
              )
        ]
        self.windows_settings.extend(mapping)

        for element in self.windows_settings:
            self.__windows_settings[element.hive_key] = element


    def windows_mapping_append(self):
        for setting_key in self.__windows_settings.keys():
            value = self.storage.get_hkcu_entry(self.sid, setting_key)
            if value:
                logging.debug(slogm('Found GSettings windows mapping {} to {}'.format(setting_key, value.data)))
                mapping = self.__windows_settings[setting_key]
                try:
                    self.gsettings.append(user_gsetting(mapping.gsettings_schema, mapping.gsettings_key, value.data))
                except Exception as exc:
                    print(exc)

    def uri_fetch_helper(self, schema, path, value):
        return uri_fetch(schema, path, value, self.file_cache)

    def run(self):
        #for setting in self.gsettings_keys:
        #    valuename = setting.hive_key.rpartition('\\')[2]
        #    rp = valuename.rpartition('.')
        #    schema = rp[0]
        #    path = rp[2]
        #    self.gsettings.append(user_gsetting(schema, path, setting.data))


        # Calculate all mapped gsettings if mapping enabled
        if self.__windows_mapping_enabled:
            logging.debug(slogm('Mapping Windows policies to GSettings policies'))
            self.windows_mapping_append()
        else:
            logging.debug(slogm('GSettings windows policies mapping not enabled'))

        # Calculate all configured gsettings
        for setting in self.gsettings_keys:
            valuename = setting.hive_key.rpartition('\\')[2]
            rp = valuename.rpartition('.')
            schema = rp[0]
            path = rp[2]
            helper = self.uri_fetch_helper if setting.hive_key.lower() == self.__wallpaper_entry.lower() else None
            if valuename == setting.data:
                valuenameArr = setting.keyname.rpartition('\\')[2]
                rpArr = valuenameArr.rpartition('.')
                schema = rpArr[0]
                path = rpArr[2]
                if self.dictArr and path in self.dictArr.keys():
                    self.dictArr[path].append(setting.data)
                    self.gsettings.pop()
                else:
                    self.dictArr[path] = [setting.data,]
                self.gsettings.append(user_gsetting(schema, path, self.dictArr[path], helper))
                continue
            self.gsettings.append(user_gsetting(schema, path, setting.data, helper))

        # Create GSettings policy with highest available priority
        for gsetting in self.gsettings:
            logging.debug(slogm('Applying user setting {}.{} to {}'.format(gsetting.schema,
                                                                           gsetting.path,
                                                                           gsetting.value)))
            gsetting.apply()

    def user_context_apply(self):
        if self.__module_enabled:
            logging.debug(slogm('Running GSettings applier for user in user context'))
            self.run()
        else:
            logging.debug(slogm('GSettings applier for user in user context will not be started'))

    def admin_context_apply(self):
        # Cache files on remote locations
        try:
            entry = self.__wallpaper_entry
            filter_result = self.storage.get_hkcu_entry(self.sid, entry)
            if filter_result:
                self.file_cache.store(filter_result.data)
        except Exception as exc:
            logdata = dict()
            logdata['exception'] = str(exc)
            logging.debug(slogm('Unable to cache specified URI for user: {}'.format(logdata)))


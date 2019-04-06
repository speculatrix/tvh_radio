#!/usr/bin/env python3
# -*- coding: utf-8 -*-
'''
Yet Another Pi Radio application.
This is a multi-mode radio app for a Pi, for streaming from the internet or from a TV Headend server
'''

import argparse
import configparser
#import datetime
#import hashlib
#import json
import os
#import stat
import signal
import sys
import subprocess
import time
from threading import Event, Thread
import select
import tty
import collections
import termios
import requests

# requires making code less readable:
# Xpylint:disable=bad-whitespace
# pylint:disable=too-many-branches
# pylint:disable=too-many-locals
# Xpylint:disable=too-many-nested-blocks
# Xpylint:disable=too-many-statements
# pylint:disable=global-statement

# broken in pylint3:
# pylint:disable=global-variable-not-assigned

##########################################################################################

URL_GITHUB_HASH_SELF = 'https://api.github.com/repos/speculatrix/ya_pi_radio/ya_pi_radio.py'

# string constants
TS_URL_CHN = 'api/channel/grid'
TS_URL_STR = 'stream/channel'

TS_URL = 'ts_url'
TS_USER = 'ts_user'
TS_PASS = 'ts_pass'
TS_PAUTH = 'ts_pauth'
TS_PLAY = 'ts_play'

TITLE = 'title'
DFLT = 'default'


# the settings file is stored in a directory under $HOME
SETTINGS_DIR = '.ya_pi_radio'
SETTINGS_FILE = 'settings.ini'
SETTINGS_SECTION = 'user'


SETTINGS_DEFAULTS = {
    TS_URL: {
        TITLE: 'URL of TV Headend Server',
        DFLT: 'http://tvh.example.com:9981',
    },
    TS_USER: {
        TITLE: 'Username on TVH server',
        DFLT: TS_USER,
    },
    TS_PASS: {
        TITLE: 'Password on TVH server',
        DFLT: TS_PASS,
    },
    TS_PAUTH: {
        TITLE: 'Persistent Auth Token',
        DFLT: TS_PAUTH,
    },
    TS_PLAY: {
        TITLE: 'Player Command Line',
        DFLT: '/usr/bin/omxplayer -o alsa',
        #DFLT: 'vlc -I dummy --novideo',
    },
}

DBG_LEVEL = 0

# Radio Modes
RM_TVH = 'TVH'
RM_STR = 'STR'
RADIO_MODE = RM_TVH # default


##########################################################################################
# help
def print_help():
    '''prints help'''

    print('''=== Help
? - help
d - down a channel
h - help
m - mode change
p - play channel
q - quit
u - up a channel
''')


##########################################################################################
def get_tvh_chan_urls():
    '''gets the channel listing and generats an ordered dict by name'''

    global DBG_LEVEL
    global MY_SETTINGS

    ts_url = MY_SETTINGS.get(SETTINGS_SECTION, TS_URL)
    ts_user = MY_SETTINGS.get(SETTINGS_SECTION, TS_USER)
    ts_pass = MY_SETTINGS.get(SETTINGS_SECTION, TS_PASS)
    ts_query = '%s/%s?limit=400' % (
        ts_url,
        TS_URL_CHN,
    )
    ts_response = requests.get(ts_query, auth=(ts_user, ts_pass))
    #print('<!-- get_channel_dict URL %s -->' % (ts_query, ))
    if ts_response.status_code != 200:
        print('>Error code %d\n%s' % (ts_response.status_code, ts_response.content, ))
        return {}

    ts_json = ts_response.json()
    #print('%s' % json.dumps(ts_json, sort_keys=True, \
    #                                   indent=4, separators=(',', ': ')) )

    if TS_PAUTH in MY_SETTINGS[SETTINGS_SECTION]:
        ts_pauth = '&AUTH=%s' % (MY_SETTINGS.get(SETTINGS_SECTION, TS_PAUTH), )
    else:
        ts_pauth = ''


    channel_map = {}  # full channel info
    channel_list = []  # build a list of channel names
    ordered_channel_map = collections.OrderedDict()
    if 'entries' in ts_json:
        # grab all channel info
        name_unknown = 0
        number_unknown = -1
        for entry in ts_json['entries']:
            # start building a dict with channel name as key
            if 'name' in entry:
                channel_name = entry['name']
            else:
                channel_name = 'unknown ' + str(name_unknown)
                name_unknown += 1

            channel_list.append(channel_name)
            if channel_name not in channel_map:
                channel_map[channel_name] = {}

            # store the channel specific info
            ch_map = channel_map[channel_name]

            if 'tags' in entry:
                ch_map['tags'] = entry['tags']

            if 'number' in entry:
                ch_map['number'] = entry['number']
            else:
                ch_map['number'] = number_unknown
                name_unknown -= 1

            ch_map['url'] = '%s/%s/%s?profile=audio-only%s' % (
                            MY_SETTINGS.get(SETTINGS_SECTION, TS_URL),
                            TS_URL_STR,
                            entry['uuid'],
                            ts_pauth, )

            if 'icon_public_url' in entry:
                ch_map['icon_public_url'] = entry['icon_public_url']

        channel_list_sorted = sorted(channel_list, key=lambda s: s.casefold())

        # case insensitive sort of channel list
        for chan in channel_list_sorted:
            # ... produces an ordered dict
            #print('adding %s<br />' % (chan, ))
            ordered_channel_map[chan] = channel_map[chan]

    return ordered_channel_map


##########################################################################################
def check_load_config_file(settings_dir, settings_file):
    '''check there's a config file which is writable;
       returns 0 if OK, -1 if the rest of the page should be aborted,
       > 0 to trigger rendering of the settings page'''

    global DBG_LEVEL
    global MY_SETTINGS

    ########
    if os.path.isfile(settings_dir):
        error_text = 'Error, "%s" is a file and not a directory' % (settings_dir, )
        return (-2, error_text)

    if not os.path.isdir(settings_dir):
        os.mkdir(settings_dir)
        if not os.path.isdir(settings_dir):
            error_text = 'Error, "%s" is not a directory' % (settings_dir, )
            return (-2, error_text)


    # verify the settings file exists and is writable
    if not os.path.isfile(settings_file):
        error_text = 'Error, can\'t open "%s" for reading' % (settings_file, )
        return(-1, error_text)

    # file is zero bytes?
    config_stat = os.stat(settings_file)
    if config_stat.st_size == 0:
        error_text = 'Error, "%s" file is empty\n' % (settings_file, )
        return(-1, error_text)

    if not MY_SETTINGS.read(settings_file):
        error_text = 'Error, failed parse config file "%s"' % (settings_file, )
        return(-1, error_text)

    return (0, 'OK')



##########################################################################################
# settings_editor
def settings_editor(settings_dir, settings_file):
    '''settings_editor'''

    global DBG_LEVEL
    global MY_SETTINGS

    (config_bad, error_text) = check_load_config_file(settings_dir, settings_file)
    if config_bad < 0:
        print('%s' % (error_text, ) )


    if SETTINGS_SECTION not in MY_SETTINGS.sections():
        print('section %s doesn\'t exit' % SETTINGS_SECTION)
        MY_SETTINGS.add_section(SETTINGS_SECTION)

    print('=== Settings ===')

    # attempt to find the value of each setting, either from the params
    # submitted by the browser, or from the file, or from the defaults
    for setting in SETTINGS_DEFAULTS:
        setting_value = ''

        try:
            setting_value = str(MY_SETTINGS.get(SETTINGS_SECTION, setting))
        except configparser.NoOptionError:
            if DFLT in SETTINGS_DEFAULTS[setting]:
                setting_value = SETTINGS_DEFAULTS[setting][DFLT]
            else:
                setting_value = ''

        print('%s [%s]: ' % (setting, setting_value, ), end='')
        sys.stdout.flush()
        new_value = sys.stdin.readline().rstrip()
        if new_value != '' and new_value != '\n':
            MY_SETTINGS.set(SETTINGS_SECTION, setting, new_value)

    config_file_handle = open(settings_file, 'w')
    if config_file_handle:
        MY_SETTINGS.write(config_file_handle)
    else:
        print('Error, failed to open and write config file "%s"' %
              (settings_file, ))
        exit(1)


##########################################################################################
# SIGINT/ctrl-c handler
def sigint_handler(_signal_number, _frame):
    '''called when signal 2 or CTRL-C hits process'''

    global DBG_LEVEL
    global QUIT_FLAG
    global EVENT
    print('\nCTRL-C QUIT')
    QUIT_FLAG = True
    EVENT.set()

##########################################################################################
def keyboard_listen_thread(event):
    '''keyboard listening thread'''

    global QUIT_FLAG
    global KEY_STROKE

    # set term to raw, so doesn't wait for return
    old_settings = termios.tcgetattr(sys.stdin)
    tty.setcbreak(sys.stdin.fileno())

    while QUIT_FLAG == 0:
        # we need a timeout just so's we occasionally check QUIT_FLAG
        readable_sockets, _o, _e = select.select([sys.stdin], [], [], 0.2)
        if readable_sockets:
            KEY_STROKE = sys.stdin.read(1)
            EVENT.set()

    # set term back to cooked
    termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_settings)


##########################################################################################
def radio_app():
    '''this runs the radio appliance'''

    global MY_SETTINGS
    global RADIO_MODE
    global EVENT
    global QUIT_FLAG
    global KEY_STROKE

    print('Error, no actual functionality yet')

    signal.signal(signal.SIGINT, sigint_handler)

    threads = []
    threads.append(Thread(target=keyboard_listen_thread, args=(EVENT, )))
    threads[-1].start()


    #if RADIO_MODE == RM_TVH:
    #    get_tvh_chan_urls()

    channel_num = 0
    max_chan = 10

    # SIGINT and keyboard strokes and (one day) GPIO events all get funnelled here
    print('radio app waiting on event')
    while not QUIT_FLAG:
        EVENT.wait() # Blocks until the flag becomes true.
        #print('Wait complete')
        if KEY_STROKE != '':
            if KEY_STROKE == 'q':
                print('Quit!')
                QUIT_FLAG = 1

            elif KEY_STROKE == '?' or KEY_STROKE == 'h':
                print_help()

            #elif KEY_STROKE == 'l':
                #DBG_LEVEL or print('list')
                #print('list')
                #print(', '.join(chan_names))

            elif KEY_STROKE == 'p':
                DBG_LEVEL or print('play')
                print('unable to play channel %d' % (channel_num, ))
                #play_channel(chan_data)

            elif KEY_STROKE == 'd':
                DBG_LEVEL or print('down')
                if channel_num > 0:
                    channel_num = channel_num - 1

            elif KEY_STROKE == 'u':
                DBG_LEVEL or print('up')
                if channel_num < max_chan - 1:
                    channel_num = channel_num + 1

            elif KEY_STROKE == 'm':
                if RADIO_MODE == RM_TVH:
                    RADIO_MODE = RM_STR
                else:
                    RADIO_MODE = RM_TVH
                print('Mode now %s' % (RADIO_MODE, ))

            else:
                print('Unknown key')

            KEY_STROKE = ''

        EVENT.clear() # Resets the flag.

    for thread in threads:
        thread.join()


##########################################################################################
def main():
    '''the main entry point'''

    DBG_LEVEL = 0

    global SETTINGS_DIR
    global SETTINGS_FILE
    global MY_SETTINGS
    global RADIO_MODE
    global EVENT
    global KEY_STROKE

    settings_dir = os.path.join(os.environ['HOME'], SETTINGS_DIR)
    settings_file = os.path.join(settings_dir, SETTINGS_FILE)

    parser = argparse.ArgumentParser()
    parser.add_argument('-d', '--debug', required=False,
                        action="store_true", help='increase the debug level')
    parser.add_argument('-s', '--setup', required=False,
                        action="store_true", help='run the setup process')

    args = parser.parse_args()

    if args.debug:
        DBG_LEVEL += 1
        print('Debug, increased debug level')

    if args.setup:
        settings_editor(settings_dir, settings_file)
    else:
        (config_bad, error_text) = check_load_config_file(settings_dir, settings_file)
        if config_bad < 0:
            print('%s' % (error_text,) )
            print('please fix the situation and re-run program with -s flag')
            exit(1)
        radio_app()


##########################################################################################

if __name__ == "__main__":
    KEY_STROKE = ''
    QUIT_FLAG = False
    EVENT = Event()
    MY_SETTINGS = configparser.ConfigParser()
    main()

# vim: tabstop=8 expandtab shiftwidth=4 softtabstop=4

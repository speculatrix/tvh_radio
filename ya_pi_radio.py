#!/usr/bin/env python3
# -*- coding: utf-8 -*-
'''
Yet Another Pi Radio application.
This is a multi-mode radio app for a Pi, for streaming from the internet or from a TV Headend server
'''

import argparse
import configparser
import copy
import datetime
#import hashlib
import json
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
import urllib

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

GOOGLE_TTS = 'http://translate.google.com/translate_tts?ie=UTF-8&client=tw-ob&tl=en&q='
G_TTS_UA = 'VLC/3.0.2 LibVLC/3.0.2'

# string constants
TS_URL_CHN = 'api/channel/grid'
TS_URL_STR = 'stream/channel'
TS_URL_PEG = 'api/passwd/entry/grid'

TS_URL = 'ts_url'
TS_USER = 'ts_user'
TS_PASS = 'ts_pass'
TS_PAUTH = 'ts_pauth'
TS_PLAY = 'ts_play'

TITLE = 'title'
DFLT = 'default'
HELP = 'help'


# the settings file is stored in a directory under $HOME
SETTINGS_DIR = '.ya_pi_radio'
SETTINGS_FILE = 'settings.ini'
SETTINGS_SECTION = 'user'


SETTINGS_DEFAULTS = {
    TS_URL: {
        TITLE: 'URL',
        DFLT: 'http://tvh.example.com:9981',
        HELP: 'This is the URL of the TV Headend Server main web interface, without the trailing slash',
    },
    TS_USER: {
        TITLE: 'User',
        DFLT: TS_USER,
        HELP: 'This is a user with API access and streaming rights',
    },
    TS_PASS: {
        TITLE: 'Pass',
        DFLT: TS_PASS,
        HELP: 'Password on TVH server',
    },
    TS_PAUTH: {
        TITLE: 'P.A.T.',
        DFLT: TS_PAUTH,
        HELP: 'The Persistent Auth Token can be found by logging into the TV headend, editing the user to set persistent auth on, then saving, then re-edit and scroll down to see the persistent auth value',
    },
    TS_PLAY: {
        TITLE: 'Player',
        DFLT: '/usr/bin/omxplayer.bin -o alsa',
        #DFLT: 'vlc -I dummy --novideo',
        HELP: 'Command to play media with arguments, try "/usr/bin/omxplayer.bin -o alsa" or "vlc -I dummy --novideo --play-and-exit"',
    },
}


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
p - play/stop channel
q - quit
s - speak channel name
t - speak time
u - up a channel
''')

##########################################################################################
def api_test_func():
    '''gets the channel listing and generats an ordered dict by name'''

    global DBG_LEVEL

    ts_url = MY_SETTINGS[SETTINGS_SECTION][TS_URL]
    ts_user = MY_SETTINGS[SETTINGS_SECTION][TS_USER]
    ts_pass = MY_SETTINGS[SETTINGS_SECTION][TS_PASS]
    ts_query = '%s/%s' % (
        ts_url,
        TS_URL_PEG,
    )
    ts_response = requests.get(ts_query, auth=(ts_user, ts_pass))
    print('<!-- get_tvh_chan_urls URL %s -->' % (ts_query, ))
    if ts_response.status_code != 200:
        print('>Error code %d\n%s' % (ts_response.status_code, ts_response.content, ))
        return

    ts_json = ts_response.json()
    #if DBG_LEVEL > 0:
    print('%s' % json.dumps(ts_json, sort_keys=True, \
                                indent=4, separators=(',', ': ')) )

 
##########################################################################################
def text_to_speech_file(input_text, output_file):
    '''uses Google to turn supplied text into speech in the file'''

    goo_url = '%s%s' % (GOOGLE_TTS, urllib.parse.quote(input_text), )
    opener = urllib.request.build_opener()
    opener.addheaders =[('User-agent', G_TTS_UA), ]

    write_handle = open(output_file, 'wb')
    with opener.open(goo_url) as goo_handle:
        write_handle.write(goo_handle.read())


##########################################################################################
def chan_data_to_tts_file(chan_data):
    '''given the channel data, returns the name of a sound file which is the
       channel name; calls text_to_speech_file to generate it if required'''

    global DBG_LEVEL
    global MY_SETTINGS

    tts_file_name = '%s.mp3' % (os.path.join(os.environ['HOME'], SETTINGS_DIR, chan_data['uuid']), )

    if not os.path.isfile(tts_file_name):
        text_to_speech_file(chan_data['name'], tts_file_name)

    return(tts_file_name)


##########################################################################################
def get_tvh_chan_urls():
    '''gets the channel listing and generats an ordered dict by name'''

    global DBG_LEVEL

    ts_url = MY_SETTINGS[SETTINGS_SECTION][TS_URL]
    ts_user = MY_SETTINGS[SETTINGS_SECTION][TS_USER]
    ts_pass = MY_SETTINGS[SETTINGS_SECTION][TS_PASS]
    ts_query = '%s/%s?limit=400' % (
        ts_url,
        TS_URL_CHN,
    )
    ts_response = requests.get(ts_query, auth=(ts_user, ts_pass))
    #print('<!-- get_tvh_chan_urls URL %s -->' % (ts_query, ))
    if ts_response.status_code != 200:
        print('>Error code %d\n%s' % (ts_response.status_code, ts_response.content, ))
        return {}

    ts_json = ts_response.json()
    if DBG_LEVEL > 0:
        print('%s' % json.dumps(ts_json, sort_keys=True, \
                                indent=4, separators=(',', ': ')) )

    if TS_PAUTH in MY_SETTINGS[SETTINGS_SECTION]:
        ts_pauth = '&AUTH=%s' % (MY_SETTINGS[SETTINGS_SECTION][TS_PAUTH], )
    else:
        ts_pauth = ''


    chan_map = {}  # full channel info
    chan_list = []  # build a list of channel names
    ordered_chan_map = collections.OrderedDict()
    if 'entries' in ts_json:
        # grab all channel info
        name_unknown = 0
        number_unknown = -1
        for entry in ts_json['entries']:
            # start building a dict with channel name as key
            if 'name' in entry:
                chan_name = entry['name']
            else:
                chan_name = 'unknown ' + str(name_unknown)
                name_unknown += 1

            chan_list.append(chan_name)
            chan_map[chan_name] = copy.deepcopy(entry)
            chan_map[chan_name]['strm_url'] = '%s/%s/%s?profile=audio-only%s' % (
                                   MY_SETTINGS[SETTINGS_SECTION][TS_URL],
                                   TS_URL_STR,
                                   entry['uuid'],
                                   ts_pauth, )


        chan_list_sorted = sorted(chan_list, key=lambda s: s.casefold())

        # case insensitive sort of channel list
        for chan in chan_list_sorted:
            # ... produces an ordered dict
            #print('adding %s<br />' % (chan, ))
            ordered_chan_map[chan] = chan_map[chan]

    if DBG_LEVEL > 0:
        print('%s' % json.dumps(ordered_chan_map, sort_keys=True, \
                                indent=4, separators=(',', ': ')) )

    return ordered_chan_map


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
            error_text = 'Error, "%s" is not a directory, couldn\'t make it one' % (settings_dir, )
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

    print('Debug, check_load_config_file: %s' % (MY_SETTINGS[SETTINGS_SECTION][TS_URL], ) )

    return (0, 'OK')



##########################################################################################
# settings_editor
def settings_editor(settings_dir, settings_file):
    '''settings_editor'''

    global DBG_LEVEL
    global MY_SETTINGS

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

        print('Hint: %s' % (SETTINGS_DEFAULTS[setting][HELP], ))
        print('%s [%s]: ' % (SETTINGS_DEFAULTS[setting][TITLE], setting_value, ), end='')
        sys.stdout.flush()
        new_value = sys.stdin.readline().rstrip()
        if new_value != '' and new_value != '\n':
            MY_SETTINGS.set(SETTINGS_SECTION, setting, new_value)
        else:
            MY_SETTINGS.set(SETTINGS_SECTION, setting, setting_value)
        print('')

    config_file_handle = open(settings_file, 'w')
    if config_file_handle:
        MY_SETTINGS.write(config_file_handle)
    else:
        print('Error, failed to open and write config file "%s"' %
              (settings_file, ))
        exit(1)


##########################################################################################
def play_time():

    now = datetime.datetime.now()
    the_time_is = now.strftime('the time is %M minutes past %H, on %b %d, %Y')
    time_file = os.path.join(os.path.join(os.environ['HOME'], SETTINGS_DIR, 'time_file.mp3'))
    text_to_speech_file(the_time_is, time_file)
    play_file(time_file)


##########################################################################################
def play_file(audio_file_name):

    global DBG_LEVEL
    global MY_SETTINGS

    play_cmd = MY_SETTINGS.get(SETTINGS_SECTION, TS_PLAY)
    play_cmd_array = play_cmd.split()
    play_cmd_array.append(audio_file_name)
    #print('Debug, play command is "%s"' % (' : '.join(play_cmd_array), ))

    subprocess.call(play_cmd_array)


##########################################################################################
# play_channel
def play_channel(event, chan_data):
    '''starts player on channel number'''

    global DBG_LEVEL
    global MY_SETTINGS
    global STOP_PLAYBACK
    global PLAYER_PID

    #print('Debug, playing channel\n%s' % json.dumps(chan_data, sort_keys=True, indent=4, separators=(',', ': ')) )

    url = chan_data['strm_url']

    play_cmd = MY_SETTINGS.get(SETTINGS_SECTION, TS_PLAY)
    play_cmd_array = play_cmd.split()
    play_cmd_array.append(url)
    print('Debug, play command is "%s"' % (' : '.join(play_cmd_array), ))

    player_proc = subprocess.Popen(play_cmd_array, shell=False)
    PLAYER_PID = player_proc.pid
    print(str(player_proc) )
    print('player pid %d' % (PLAYER_PID, ))
    player_active = True
    while player_active:
        try:
            player_proc.wait(timeout=1)
            #print('Player finished')
            player_active = False
            STOP_PLAYBACK = False
            PLAYER_PID = 0

        except subprocess.TimeoutExpired:
            pass
            #print('Player still running')

        if STOP_PLAYBACK:
            player_proc.kill()

    print('play_channel exiting')

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
    '''keyboard listening thread, sets raw input and uses sockets to
       get single key strokes without waiting, triggering an event.'''

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
    global STOP_PLAYBACK
    global PLAYER_PID

    signal.signal(signal.SIGINT, sigint_handler)

    threads = []
    threads.append(Thread(target=keyboard_listen_thread, args=(EVENT, )))
    threads[-1].start()

    chan_dict = {}
    if RADIO_MODE == RM_TVH:
        chan_map = get_tvh_chan_urls()
    else:
        print('Sorry, only TVH supported')

    chan_num = 0
    chan_names = list(chan_map.keys())
    max_chan = len(chan_map)

    # SIGINT and keyboard strokes and (one day) GPIO events all get funnelled here
    print('radio app waiting on event')
    while not QUIT_FLAG:
        EVENT.wait() # Blocks until the flag becomes true.
        #print('Wait complete')
        if KEY_STROKE != '':
            if KEY_STROKE == 'A':   # secret key code :-)
                api_test_func()
                
            elif KEY_STROKE == 'q':
                print('Quit!')
                while PLAYER_PID != 0:
                    print('Waiting to stop playback')
                    STOP_PLAYBACK = True
                    time.sleep(1)

                QUIT_FLAG = 1

            elif KEY_STROKE == '?' or KEY_STROKE == 'h':
                print_help()

            #elif KEY_STROKE == 'l':
                #DBG_LEVEL and print('list')
                #print('list')
                #print(', '.join(chan_names))

            elif KEY_STROKE == 'p':
                DBG_LEVEL or print('play')
                if PLAYER_PID == 0:
                    print('attempting to play channel %d/%s' % (chan_num, chan_names[chan_num],))
                    chan_data = chan_map[chan_names[chan_num]]
                    #play_channel(chan_data)
                    threads = []
                    threads.append(Thread(target=play_channel, args=(EVENT, chan_data, ) ))
                    threads[-1].start()
                else:
                    print('Setting STOP_PLAYBACK true')
                    STOP_PLAYBACK = True


            elif KEY_STROKE == 'd':
                DBG_LEVEL and print('down')
                if chan_num > 0:
                    chan_num = chan_num - 1
                print('Channel %s' % (chan_names[chan_num], ))

            elif KEY_STROKE == 's':
                tts_file = chan_data_to_tts_file(chan_map[chan_names[chan_num]])
                play_file(tts_file)

            elif KEY_STROKE == 't':
                play_time()

            elif KEY_STROKE == 'u':
                DBG_LEVEL and print('up')
                if chan_num < max_chan - 1:
                    chan_num = chan_num + 1
                print('Channel %s' % (chan_names[chan_num], ))

            elif KEY_STROKE == 'm':
                if RADIO_MODE == RM_TVH:
                    RADIO_MODE = RM_STR
                else:
                    RADIO_MODE = RM_TVH
                    get_tvh_chan_urls()
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
    global STOP_PLAYBACK
    global PLAYER_PID

    # settings_file is the fully qualified path to the settings file
    settings_dir = os.path.join(os.environ['HOME'], SETTINGS_DIR)
    settings_file = os.path.join(settings_dir, SETTINGS_FILE)
    (config_bad, error_text) = check_load_config_file(settings_dir, settings_file)

    parser = argparse.ArgumentParser()
    parser.add_argument('-d', '--debug', required=False,
                        action="store_true", help='increase the debug level')
    parser.add_argument('-s', '--setup', required=False,
                        action="store_true", help='run the setup process')
    args = parser.parse_args()

    if args.debug:
        DBG_LEVEL += 1
        print('Debug, increased debug level')

    if args.setup or config_bad < 0:
        if config_bad < -1:
            print('Error, severe problem with settings, please fix and restart program')
            print('%s' % (error_text,) )
            exit(1)
        if config_bad < 0:
            print('%s' % (error_text,) )
        settings_editor(settings_dir, settings_file)
    else:
        radio_app()


##########################################################################################

if __name__ == "__main__":
    DBG_LEVEL = 0
    KEY_STROKE = ''
    QUIT_FLAG = False
    STOP_PLAYBACK = False
    PLAYER_PID = 0

    EVENT = Event()
    MY_SETTINGS = configparser.ConfigParser()
    main()

# vim: tabstop=8 expandtab shiftwidth=4 softtabstop=4

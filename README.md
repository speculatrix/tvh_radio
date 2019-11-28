# The ya_pi_radio Project

Yet Another Pi Radio application

# Purpose

This project is for allowing a Raspberry Pi to be used as a radio-like
appliance, streaming from a TV Headend server or from a list of URLs (TBD).

That said, it isn't limited to being run on a Pi, you can run it anywhere you
can run Python. I use it on my laptop which runs Fedora, but it should run on
any linux distro which supports a modern python3.

The software here is a command line interface, so that the Pi can be used
headless with just a keyboard. This project will be expanded to include
instructions on fitting into a re-purposed radio shell, and setting the
Pi to boot straight into this application.

I wrote this partly to stretch my python skills, but mostly because I wanted
to be able to turn a Raspberry Pi0/W into the basis of a streaming receiver.

This one is a little different. 
* Firstly, it understands the TV Headend API, thus allowing you to use a TVH server as a radio source.
* Secondly, it can speak to tell you the channel you're about to play.
* Thirdly, it can tell you the time.



# Installation

## Pre-Requisites

Acquire a Raspberry Pi, power supply and memory card. 

* Install Raspbian onto the card
* Power up the Pi whilst connected to a display
* Configure the WiFi
* Set the password of the pi user
* Install all updates


## TV Headend

### TL;DR: create an "audio-only" profile

We want the most efficient stream possible, which means getting the TVH
server to only pass on the audio channel. This reduces the CPU load on
the player and reduces bandwifth. On a Raspberry-Pi, it allows the
omxplayer player to be used, which otherwise croaks if given a stream
which contains video in a non-n264 codec.

Login to TVH as an administrator, and open the Configuration tab, choose
Stream, then choose Stream Profiles. Add a stream, starting with the
type Audio, set the name to audio-only, and click Apply.
 
![Audio-Only Profile](https://raw.githubusercontent.com/speculatrix/ya_pi_radio/master/create_audio_only_profile.png)


### Create a user with persistent authentication token

Create a user for playing media, enabling persistent authentication, and copy
off the username and the token and put into the settings.

![Audio-Only Profile](https://raw.githubusercontent.com/speculatrix/ya_pi_radio/master/webby_user.png)



## Getting the program

* git clone this repository
* make ya_pi_radio.py executable, 


## Running the program

* run it
* on first run, you have to go through setup, so provide the settings
* follow the onscreen instructions
* if you need to redo the settings, run it again with the -s option to go into settings



## Road Map

I intend to make the key presses customisable, so you could, say, use a
numeric USB key pad to operate it. Also, to make it possible to use GPIOs
and switches instead of a USB button board, something like the Display-O-Tron Hat:
https://thepihut.com/collections/raspberry-pi-hats/products/display-o-tron-hat

I also intend to make it possible to use a small LCD display to give status.


... end ...

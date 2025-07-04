# MP4MUSEUM
MP4MUSEUM.org Media Player dballsworth fork for remote control

## 🧪 Development Outside Raspberry Pi

To enable development on a Mac, VM, or other non-Raspberry Pi system:

- The `fake_rpi/` module contains a mocked version of `RPi.GPIO`
- It is automatically used when the real `RPi.GPIO` is not available
- This allows development and testing without hardware

You can safely leave `fake_rpi/` in the repo — it's small, isolated, and ignored in production use.


Version 6 is out! 

- sync mode via omxplayer-sync


__visit [mp4museum.org](http://mp4museum.org) for more information and a bootable image__ 

_Or an answer may reside in the [closed issues](https://github.com/JuliusCode/MP4MUSEUM/issues?q=is%3Aissue+is%3Aclosed)_



For the Python script to run on a fresh [Raspberry Pi OS Lite](https://www.raspberrypi.com/software/operating-systems/) you need to install some things

`sudo apt-get -y install vlc python3-pip`

`pip3 install python-vlc RPi.GPIO`

omx-player sync needs to be installed for sync mode (it's here on github)

if you are using the distributed image, .bashrc will run mp4museum.py

login via ssh user pi at mp4museum.local, password mp4museum

local login: press ctrl&C to get to the console

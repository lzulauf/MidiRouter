# Midi Router
Allows yaml-based configuration of usb midi routing.

Designed to be run on a Raspberry Pi (3b/4/5) to support routing usb midi messages between multiple devices.

# Installation
## Prereqs
```bash
$ sudo apt-get install git libjack-dev
```

## Setup Virtual Environment
```bash
$ python3 -m venv midi-router-venv
$ source midi-router-venv/bin/activate
```
## Install MidiRouter
```bash
$ git clone https://github.com/lzulauf/MidiRouter
$ cd MidiRouter
$ pip install -e .
```

# Usage
## Creating a config file
You will first need a configuration file. You can use the generate-config command to generate a starter config. You can then modify this to your liking.
```bash
$ midi-router generate-config
```

## Start midi-router
```bash
$ midi-router start
```

# Running on startup
You can also set midi-router to run on startup. The following instructions assume you are running a Raspberry Pi with Raspberry Pi OS (Bookworm).

> ❗️ Hardcoded paths
>
> The midi-router.service file contains hardcoded paths to the midi-router script (as well as config and log files). You may need to update the paths on the ExecStart line.
>
> You can determine the path to midi-router using `which midi-router`

```bash
$ sudo cp setup/midi-router.service /lib/systemd/system/midi-router.service
$ sudo chmod 644 /lib/systemd/system/midi-router.
$ sudo systemctl daemon-reload
$ sudo systemctl enable midi-router.service
```

You can then restart your system
```bash
$ sudo reboot
```

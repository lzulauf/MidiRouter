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
## Overview
```
usage: midi-router [-h] [--verbose] {start,info,generate-config} ...

positional arguments:
  {start,info,generate-config}
    start               Start the midi router
    info                Display midi info
    generate-config     Generate example config file

options:
  -h, --help            show this help message and exit
  --verbose, -v
```

Help can be displayed for any of the commands by appending `--help` to the command.

Additionally, the program can be made more verbose by specifying `-v`.
Additional verbose commands are cumulative, so `-vv` will make it more verbose.
The verbose flags must be placed before the command.

i.e.
```bash
$ midi-router -vv start
```
rather than
```bash
$ midi-router start -vv
```

## Creating a config file
You will first need a configuration file. You can use the generate-config command to generate a starter config. You can then modify this to your liking.
```bash
$ midi-router generate-config
```
or
```bash
$ midi-router generate-config -c my-config.yaml
```

Full help
```bash
$ midi-router generate-config --help
usage: midi-router generate-config [-h] [--config FILE]

options:
  -h, --help            show this help message and exit
  --config FILE, -c FILE
                        Config file to use [config.yaml]
```

## Start midi-router
midi-router can be started manually by running the start command. See Running
on startup for information on how to have midi-router start automatically.

```bash
$ midi-router start
```
or
```bash
$ midi-router start -c my-config.yaml
```

Full help
```bash
$ midi-router start --help
usage: midi-router start [-h] [--config FILE]

options:
  -h, --help            show this help message and exit
  --config FILE, -c FILE
                        Config file to use [config.yaml]
```

## Get midi info
midi-router can provide some basic information about midi ports on the system via the info command.

This is a simple wrapper around the mido interfaces. Additional midi
information can be obtained on the command line by interacting with the
system's amidi command directly.

```bash
$ midi-router info
MIDI Input Ports:
  Midi Through:Midi Through Port-0 14:0
  Cre8audioNiftyCASE:Cre8audioNiftyCASE MIDI 1 20:0
  Arturia MiniLab mkII:Arturia MiniLab mkII MIDI 1 24:0
  Cre8audioNiftyCASE:Cre8audioNiftyCASE MIDI 1 28:0
  Arturia BeatStep Pro:Arturia BeatStep Pro Arturia Be 32:0
  Arturia BeatStep Pro:Arturia BeatStep Pro BeatStepPr 32:1
  RtMidiOut Client:RtMidi output 131:0
  RtMidiOut Client:RtMidi output 132:0
  RtMidiOut Client:RtMidi output 133:0
MIDI Output Ports:
  Midi Through:Midi Through Port-0 14:0
  Cre8audioNiftyCASE:Cre8audioNiftyCASE MIDI 1 20:0
  Arturia MiniLab mkII:Arturia MiniLab mkII MIDI 1 24:0
  Cre8audioNiftyCASE:Cre8audioNiftyCASE MIDI 1 28:0
  Arturia BeatStep Pro:Arturia BeatStep Pro Arturia Be 32:0
  Arturia BeatStep Pro:Arturia BeatStep Pro BeatStepPr 32:1
  RtMidiIn Client:RtMidi input 129:0
  RtMidiIn Client:RtMidi input 130:0
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
$ sudo chmod 644 /lib/systemd/system/midi-router.service
$ sudo systemctl daemon-reload
$ sudo systemctl enable midi-router.service
```

You can then restart your system
```bash
$ sudo reboot
```

Logs can be viewed using journalctl
```bash
$ sudo journalctl -u midi-router.service
```

# Configuration
Configuration is performed by listing a number of port specifies and giving a short identifier string to each one. These identifiers can then be used in the mappings section to determine how midi message are routed. Mappers can determine which devices route to which other devices, filtering by channels, and allow mapping channels on one device to different channels on another device.

Here is an example configuration file that is performing routing between a MiniLab, Beat Step Pro, and two NiftyCASEs. I've added comments to more easily identify groups of related mappings.
```yaml
ports:
  inputs:
    - identifier: in_minilab
      name: Arturia MiniLab mkII:Arturia MiniLab mkII MIDI 1
      port_type: USB
    - identifier: in_bsp
      name: Arturia BeatStep Pro:Arturia BeatStep Pro Arturia Be
      port_type: USB
  outputs:
    - identifier: out_bsp
      name: Arturia BeatStep Pro:Arturia BeatStep Pro Arturia Be
      port_type: USB
    - identifier: out_nifty1
      name: Cre8audioNiftyCASE:Cre8audioNiftyCASE MIDI 1
      port_type: USB
    - identifier: out_nifty2
      name: Cre8audioNiftyCASE:Cre8audioNiftyCASE MIDI 1
      port_type: USB
mappings:

  ##################
  # Minilab to BSP #
  ##################
  - from_port:
      identifier: in_minilab
    to_port:
      identifier: out_bsp
    from_channel: 0
    to_channel: 0
  - from_port:
      identifier: in_minilab
    to_port:
      identifier: out_bsp
    from_channel: 1
    to_channel: 1
  
  #####################
  # Minilab to Nifty2 #
  #####################
  - from_port:
      identifier: in_minilab
    to_port:
      identifier: out_nifty2
    from_channel: 2
    to_channel: 0
  - from_port:
      identifier: in_minilab
    to_port:
      identifier: out_nifty2
    from_channel: 3
    to_channel: 1
  
  #################
  # BSP to Nifty1 #
  #################
  - from_port:
      identifier: in_bsp
    to_port:
      identifier: out_nifty1
    from_channel: 0
    to_channel: 0
  - from_port:
      identifier: in_bsp
    to_port:
      identifier: out_nifty1
    from_channel: 1
    to_channel: 1
  - from_port:
      identifier: in_bsp
    to_port:
      identifier: out_nifty1
    from_channel: 9
    to_channel: 9

  #################
  # BSP to Nifty2 #
  #################
  - from_port:
      identifier: in_bsp
    to_port:
      identifier: out_nifty2
    from_channel: 10
    to_channel: 10
```

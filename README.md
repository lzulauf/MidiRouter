# Midi Router
Allows yaml-based configuration of usb midi routing.

# Installation
```bash
$ git clone https://github.com/lzulauf/MidiRouter
$ cd MidiRouter
$ pip install -e .
```

# Usage
## Creating a config file
You will first need a configuration file. You can use the create-config command to generate a starter config. You can then modify this to your liking.
```bash
$ midi-router create-config
```

## Start midi-router
```bash
$ midi-router start
```

# Running on startup
You can also set midi-router to run on startup. The following instructions assume you are running a Raspberry Pi with Raspberry Pi OS (Bookworm).

```bash
$ sudo cp setup/midi-router.service /lib/systemd/system/midi-router.service
$ sudo chmod 644 /lib/systemd/system/midi-router.
$ sudo systemctl daemon-reload
$ sudo systemctl enable midi-router.service
```
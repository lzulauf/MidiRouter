import argparse
import logging
import sys

import mido

from midi_router.config import Config
from midi_router.config_generator import generate_default_config
from midi_router.midi_router import MidiRouter

LOG_LEVELS = [
    # logging.CRITICAL,
    # logging.ERROR,
    logging.WARNING,
    logging.INFO,
    logging.DEBUG,
]


class CommandLine:
    def __init__(self, args):
        self.args = args

    def print_info(self):
        print("MIDI Input Ports:")
        print("  " + "\n  ".join(mido.get_input_names()))
        print("MIDI Output Ports:")
        print("  " + "\n  ".join(mido.get_output_names()))

    def write_default_config(self):
        print(f"Writing to {self.args.config.name}")
        generate_default_config().to_yaml(stream=self.args.config)

    def start(self):
        print(f"Starting using config {self.args.config.name}")
        config = Config.from_yaml(stream=self.args.config)
        router = MidiRouter(config)
        router.run()

    def run(self):
        if self.args.cmd == 'info':
            self.print_info()
        elif self.args.cmd == 'generate-config':
            self.write_default_config()
        elif self.args.cmd == 'start':
            self.start()


def main(argv=None):
    """%(prog)s"""
    argv = argv or sys.argv[1:]
    parser = argparse.ArgumentParser(usage=CommandLine.__init__.__doc__)
    parser.add_argument("--verbose", "-v", action="count", default=0)
    parser.set_defaults(cmd=None)
    subparsers = parser.add_subparsers()

    start_parser = subparsers.add_parser('start', help="Start the midi router")
    start_parser.set_defaults(cmd='start')
    start_parser.add_argument('--config', '-c', metavar='FILE', type=argparse.FileType('r'), default='config.yaml', help='Config file to use [%(default)s]')
    
    info_parser = subparsers.add_parser('info', help="Display midi info")
    info_parser.set_defaults(cmd='info')
    
    generate_config_parser = subparsers.add_parser('generate-config', help='Generate example config file')
    generate_config_parser.set_defaults(cmd='generate-config')
    generate_config_parser.add_argument('--config', '-c', metavar='FILE', type=argparse.FileType('w'), default='config.yaml', help='Config file to use [%(default)s]')
    
    args = parser.parse_args(argv)
    logging.basicConfig(level=LOG_LEVELS[args.verbose])
    if args.cmd is None:
        parser.print_help()

    CommandLine(args).run()

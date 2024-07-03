import contextlib
import itertools
import logging
import time

import mido
try:
    from rtmidi import SystemError as RTMidiSystemError
except ImportError:
    class RTMidiSystemError(Exception):
        """Dummy class to catch when rtmidi isn't available."""

from midi_router import config


logger = logging.getLogger("midi_router")


def _open_input_port(long_name):
    try:
        return mido.open_input(long_name)
    except RTMidiSystemError as e:
        logger.warning(repr(e))


def _open_output_port(long_name):
    try:
        return mido.open_output(long_name)
    except RTMidiSystemError as e:
        logger.warning(repr(e))


def _open_input_ports(used_input_long_names):
    return {
        long_name: _open_input_port(long_name)
        for long_name in used_input_long_names
    }


def _open_output_ports(used_output_long_names):
    return {
        long_name: _open_output_port(long_name)
        for long_name in used_output_long_names
    }


class MidiRouter:
    def __init__(self, config):
        self.config = config

    def _get_identifiers_to_port_infos(self):
        identifiers_to_input_port_infos = {
            port_info.identifier: port_info
            for port_info in self.config.ports.inputs
        }
        identifiers_to_output_port_infos = {
            port_info.identifier: port_info
            for port_info in self.config.ports.outputs
        }
        return identifiers_to_input_port_infos, identifiers_to_output_port_infos

    def _get_used_port_names(self, identifiers_to_input_ports, identifiers_to_output_ports):
        if any(
            mapping.from_port == config.PortConstant.ALL
            for mapping in self.config.mappings
        ):
            used_input_long_names = set(mido.get_input_names())
        else:
            used_input_long_names = {
                identifiers_to_input_ports[mapping.from_port.identifier].long_name
                for mapping in self.config.mappings
                if isinstance(mapping.from_port, config.PortSpecifier)
            }

        if any(
            mapping.to_port == config.PortConstant.ALL
            for mapping in self.config.mappings
        ):
            used_output_long_names = set(mido.get_output_names())
        else:
            used_output_long_names = {
                identifiers_to_output_ports[mapping.to_port.identifier].long_name
                for mapping in self.config.mappings
                if isinstance(mapping.to_port, config.PortSpecifier)
            }
        return used_input_long_names, used_output_long_names

    def _loop(self, mappings_by_input_port, output_ports_by_long_name, identifiers_to_output_port_infos):
        for input_port, mappings in mappings_by_input_port.items():
            # print(f"{input_port=}")
            message = ''
            while True:
                print(time.perf_counter())
                message = input_port.receive(block=False)
                if message is None:
                    break
                print(f"{input_port.name}: {message}")

                # TODO replace mappings with "compiled" mappings that contain (transformer, output_port(s))
                for mapping in mappings:
                    if mapping.to_port == config.PortConstant.ALL: 
                        print(f"to ALL: {message}")
                        for output_port in output_ports_by_long_name.values():
                            output_port.send(message)
                    else:
                        print(f"to {mapping.to_port}: {message}")
                        output_ports_by_long_name[identifiers_to_output_port_infos[mapping.to_port].long_name].send(message)
                    
        
        
    def run(self):
        identifiers_to_input_port_infos, identifiers_to_output_port_infos = self._get_identifiers_to_port_infos()
        used_input_long_names, used_output_long_names = self._get_used_port_names(identifiers_to_input_port_infos, identifiers_to_output_port_infos)   
        input_ports_by_long_name = _open_input_ports(used_input_long_names)
        output_ports_by_long_name = _open_output_ports(used_output_long_names)
        print(f"{input_ports_by_long_name=}")
        mappings_by_input_port = {
            port: []
            for port in input_ports_by_long_name.values()
        }
        for mapping in self.config.mappings:
            if mapping.from_port == config.PortConstant.ALL:
                for mapping_list in mappings_by_input_port.values():
                    mapping_list.append(mapping)
            else:
                mappings_by_input_port[input_ports_by_long_name[identifiers_to_input_port_infos[mapping.from_port.identifier].long_name]].append(mapping)

        #input_ports_and_multiplexers = [
        #    (port, self.._generate_multiplexers(mapping))
        #    for port, mappings in mappings_by_input_port.items()
        #]
                
        print(mappings_by_input_port)
        import time
        try:
            start_time = time.perf_counter()
            cur_time = start_time
            loops = 0
            while cur_time < start_time + 10:
                self._loop(mappings_by_input_port, output_ports_by_long_name, identifiers_to_output_port_infos)
                cur_time = time.perf_counter()
                loops += 1
            print(f"{loops=}")
        finally:
            for port in itertools.chain(input_ports_by_long_name.values(), output_ports_by_long_name.values()):
                port.close()


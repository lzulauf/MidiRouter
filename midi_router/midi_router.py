import collections
import itertools
import logging
import queue

import mido
try:
    from rtmidi import SystemError as RTMidiSystemError
except ImportError:
    class RTMidiSystemError(Exception):
        """Dummy class to catch when rtmidi isn't available."""

from midi_router import config


logger = logging.getLogger("midi_router")


IncomingMessage = collections.namedtuple("IncomingMessage", ["input_port_name", "message"])


class MidiRouter:
    def __init__(self, config):
        self.config = config
        self.incoming_message_queue = queue.Queue()

    def create_receive_message_callback(self, input_port_name):
        def _receive_message_callback(message):
            self.incoming_message_queue.put(IncomingMessage(input_port_name, message))
        return _receive_message_callback

    def _open_input_port(self, long_name):
        try:
            return mido.open_input(long_name, callback=self.create_receive_message_callback(long_name))
        except RTMidiSystemError as e:
            logger.warning(repr(e))

    def _open_output_port(self, long_name):
        try:
            return mido.open_output(long_name)
        except RTMidiSystemError as e:
            logger.warning(repr(e))

    def _open_input_ports(self, used_input_long_names):
        return {
            long_name: self._open_input_port(long_name)
            for long_name in used_input_long_names
        }

    def _open_output_ports(self, used_output_long_names):
        return {
            long_name: self._open_output_port(long_name)
            for long_name in used_output_long_names
        }

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

    def _loop(self, mappings_by_input_port_name, output_ports_by_long_name, identifiers_to_output_port_infos):
        input_port_name, message = self.incoming_message_queue.get()
        for mapping in mappings_by_input_port_name[input_port_name]:
            if mapping.to_port == config.PortConstant.ALL: 
                logger.info(f"to ALL: {message}")
                for output_port in output_ports_by_long_name.values():
                    # Don't send messages back to the originating device
                    if output_port.name != input_port_name:
                        output_port.send(message)
            else:
                output_port = output_ports_by_long_name[identifiers_to_output_port_infos[mapping.to_port.identifier].long_name]                    
                logger.info(f"to {output_port.name}: {message}")
                output_port.send(message)

    def run(self):
        identifiers_to_input_port_infos, identifiers_to_output_port_infos = self._get_identifiers_to_port_infos()
        used_input_long_names, used_output_long_names = self._get_used_port_names(identifiers_to_input_port_infos, identifiers_to_output_port_infos)   
        input_ports_by_long_name = self._open_input_ports(used_input_long_names)
        output_ports_by_long_name = self._open_output_ports(used_output_long_names)
        
        mappings_by_input_port_name = {
            name: []
            for name in input_ports_by_long_name.keys()
        }
        for mapping in self.config.mappings:
            if mapping.from_port == config.PortConstant.ALL:
                for mapping_list in mappings_by_input_port_name.values():
                    mapping_list.append(mapping)
            else:
                mappings_by_input_port_name[identifiers_to_input_port_infos[mapping.from_port.identifier].long_name].append(mapping)

        try:
            while True:
                self._loop(mappings_by_input_port_name, output_ports_by_long_name, identifiers_to_output_port_infos)
        finally:
            for port in itertools.chain(input_ports_by_long_name.values(), output_ports_by_long_name.values()):
                port.close()


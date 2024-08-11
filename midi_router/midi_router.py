import asyncio
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


class MidiDeviceChangeException(Exception):
    pass


# Worst-case time between device change checks is the sleep time plus how long
# we wait to receive a midi message (plus processing time)
#
# Increasing the queue get timeout increases performance by processing events as
# soon as their availble, but with the tradeoff of checking device changes less
# frequently.
EVENT_QUEUE_GET_TIMEOUT = 0.6
MIDI_DEVICE_CHANGE_CHECK_SLEEP = 0.6


class MidiRouter:
    def __init__(self, config):
        self.config = config
        self.incoming_message_queue = queue.Queue()

    def run(self):
        # Every time the midi devices change, re-initialize
        while True:
            try:
                self._run()
            except MidiDeviceChangeException:
                logger.warn("Midi Device Change Detected. Re-initializing")

    def _run(self):
        identifiers_to_input_port_infos, identifiers_to_output_port_infos = self._get_identifiers_to_port_infos()
        used_input_long_names, used_output_long_names = self._get_used_port_names(identifiers_to_input_port_infos, identifiers_to_output_port_infos)   

        input_ports_by_long_name = {}
        output_ports_by_long_name = {}
        try:
            for long_name in used_input_long_names:
                input_ports_by_long_name[long_name] = self._open_input_port(long_name)

            for long_name in used_output_long_names:
                output_ports_by_long_name[long_name] = self._open_output_port(long_name)

            mappings_by_input_port_name = self._create_mappings_by_input_port_name(identifiers_to_input_port_infos, input_ports_by_long_name)
            
            asyncio.run(self._run_async(mappings_by_input_port_name, output_ports_by_long_name, identifiers_to_output_port_infos))
        finally:
            for port in itertools.chain(input_ports_by_long_name.values(), output_ports_by_long_name.values()):
                port.close()

    async def _run_async(self, mappings_by_input_port_name, output_ports_by_long_name, identifiers_to_output_port_infos):
        monitor_midi_device_change_task = asyncio.create_task(self._monitor_midi_device_changes())
        process_message_queue_task = asyncio.create_task(self._process_message_queue(mappings_by_input_port_name, output_ports_by_long_name, identifiers_to_output_port_infos))
        await monitor_midi_device_change_task
        await process_message_queue_task

    async def _process_message_queue(self, mappings_by_input_port_name, output_ports_by_long_name, identifiers_to_output_port_infos):
        while True:
            try:
                incoming_message = self.incoming_message_queue.get(timeout=EVENT_QUEUE_GET_TIMEOUT)
            except queue.Empty:
                pass
            else:
                input_port_name, message = incoming_message
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
            await asyncio.sleep(0)  # Cooperative parallelism

    async def _monitor_midi_device_changes(self):
        old_port_names = (mido.get_input_names(), mido.get_output_names())
        while True:
            new_port_names = (mido.get_input_names(), mido.get_output_names())
            if old_port_names != new_port_names:
                raise MidiDeviceChangeException()
            await asyncio.sleep(MIDI_DEVICE_CHANGE_CHECK_SLEEP)  # Cooperative parallelism plus wait


    def _create_mappings_by_input_port_name(self, identifiers_to_input_port_infos, input_ports_by_long_name):
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
        return mappings_by_input_port_name


    def _create_receive_message_callback(self, input_port_name):
        def _receive_message_callback(message):
            self.incoming_message_queue.put(IncomingMessage(input_port_name, message))
        return _receive_message_callback

    def _open_input_port(self, long_name):
        try:
            return mido.open_input(long_name, callback=self._create_receive_message_callback(long_name))
        except RTMidiSystemError as e:
            logger.warning(repr(e))

    def _open_output_port(self, long_name):
        try:
            return mido.open_output(long_name)
        except RTMidiSystemError as e:
            logger.warning(repr(e))

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

    def _get_used_port_names(self, identifiers_to_input_port_infos, identifiers_to_output_port_infos):
        available_input_names, available_output_names = mido.get_input_names(), mido.get_output_names()
        if any(
            mapping.from_port == config.PortConstant.ALL
            for mapping in self.config.mappings
        ):
            used_input_long_names = set(
                port_info.long_name
                for port_info in identifiers_to_input_port_infos.values()
                if port_info.long_name in available_input_names
            )
        else:
            used_input_long_names = {
                identifiers_to_input_port_infos[mapping.from_port.identifier].long_name
                for mapping in self.config.mappings
                if (
                    isinstance(mapping.from_port, config.PortSpecifier) and
                    identifiers_to_input_port_infos[mapping.from_port.identifier].long_name in available_input_names
                )
            }

        if any(
            mapping.to_port == config.PortConstant.ALL
            for mapping in self.config.mappings
        ):
            used_output_long_names = set(
                port_info.long_name
                for port_info in identifiers_to_output_port_infos.values()
                if port_info.long_name in available_output_names
            )
        else:
            used_output_long_names = {
                identifiers_to_output_port_infos[mapping.to_port.identifier].long_name
                for mapping in self.config.mappings
                if (
                    isinstance(mapping.to_port, config.PortSpecifier) and
                    identifiers_to_output_port_infos[mapping.to_port.identifier].long_name in available_output_names
                )
            }
        return used_input_long_names, used_output_long_names

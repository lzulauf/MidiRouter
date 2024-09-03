import asyncio
import collections
import itertools
import json
import logging
import queue

import mido
try:
    from rtmidi import SystemError as RTMidiSystemError
except ImportError:
    class RTMidiSystemError(Exception):
        """Dummy class to catch when rtmidi isn't available."""

from midi_router import config
from midi_router.mapper import Mapper


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
        input_port_names_by_identifier = self._get_identifiers_to_port_names(mido.get_input_names(), self.config.ports.inputs)
        output_port_names_by_identifier = self._get_identifiers_to_port_names(mido.get_output_names(), self.config.ports.outputs)


        input_ports_by_identifier = {}
        output_ports_by_identifier = {}
        try:
            for identifier, port_name in input_port_names_by_identifier.items():
                input_ports_by_identifier[identifier] = self._open_input_port(port_name)

            for identifier, port_name in output_port_names_by_identifier.items():
                output_ports_by_identifier[identifier] = self._open_output_port(port_name)

            mappers_by_input_port_name = self._create_mappers_by_input_port_name(input_ports_by_identifier, output_ports_by_identifier)
            
            logger.debug(f"input_port_names_by_identifier={json.dumps(input_port_names_by_identifier, indent=2)}")
            logger.debug(f"output_port_names_by_identifier={json.dumps(output_port_names_by_identifier, indent=2)}")
            logger.debug(f"input_ports_by_identifier={json.dumps({k: v.name for k, v in input_ports_by_identifier.items()}, indent=2)}")
            logger.debug(f"output_ports_by_identifier={json.dumps({k: v.name for k, v in output_ports_by_identifier.items()}, indent=2)}")
            logger.debug(
                "mappers_by_input_port_name=" + 
                json.dumps(
                    {
                        k:[v.dict() for v in value] for k, value in mappers_by_input_port_name.items()
                    },
                    indent=2
                ))

            asyncio.run(self._run_async(mappers_by_input_port_name))

        finally:
            for port in itertools.chain(input_ports_by_identifier.values(), output_ports_by_identifier.values()):
                port.close()

    async def _run_async(self, mappers_by_input_port_name):
        monitor_midi_device_change_task = asyncio.create_task(self._monitor_midi_device_changes())
        process_message_queue_task = asyncio.create_task(self._process_message_queue(mappers_by_input_port_name))
        await monitor_midi_device_change_task
        await process_message_queue_task

    async def _process_message_queue(self, mappers_by_input_port_name):
        while True:
            try:
                incoming_message = self.incoming_message_queue.get(timeout=EVENT_QUEUE_GET_TIMEOUT)
            except queue.Empty:
                pass
            else:
                input_port_name, message = incoming_message
                if hasattr(message, "channel"):
                    logger.info(f"from {input_port_name}: {message}")
                for mapper in mappers_by_input_port_name.get(input_port_name, []):
                    mapper.send(input_port_name, message)
                if hasattr(message, "channel"):
                    logger.info("\n")
            await asyncio.sleep(0)  # Cooperative parallelism

    async def _monitor_midi_device_changes(self):
        old_port_names = (mido.get_input_names(), mido.get_output_names())
        while True:
            new_port_names = (mido.get_input_names(), mido.get_output_names())
            if old_port_names != new_port_names:
                raise MidiDeviceChangeException()
            await asyncio.sleep(MIDI_DEVICE_CHANGE_CHECK_SLEEP)  # Cooperative parallelism plus wait

    def _create_mappers_by_input_port_name(self, input_ports_by_identifier, output_ports_by_identifier):
        mappers_by_input_port_name = {
            port.name: []
            for port in input_ports_by_identifier.values()
        }
        for mapping_config in self.config.mappings:
            mapper = Mapper.from_mapping_config(mapping_config, input_ports_by_identifier,
                                                                output_ports_by_identifier)
            if mapping_config.from_port == config.PortConstant.ALL:
                for mapper_list in mappers_by_input_port_name.values():
                    mapper_list.append(mapper)
            else:
                long_name = input_ports_by_identifier[mapping_config.from_port.identifier].name
                mapper_list = mappers_by_input_port_name.get(long_name)
                # configs might reference disconnected devices, but mapper_lists only exist for connected
                # devices.
                if mapper_list is not None:
                    mapper_list.append(mapper)
        return mappers_by_input_port_name

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

    def _get_identifiers_to_port_names(self, available_port_names, port_infos):
        """
        Create a mapping that assigns every port_info to a unique port.

        This ensures that ports with only short names (no port numbers) will each
        be allocated a different port (if available).
        """
        # 1. Map all short names to lists of available long names
        available_short_names_to_long_names = {}
        for long_name in available_port_names:
            short_name, _ = config.Port.parse_long_port_name(long_name)
            available_short_names_to_long_names.setdefault(short_name, [])
            available_short_names_to_long_names[short_name].append(long_name)

        logger.debug(f"available_long_names before assigning long-named identifiers: {available_short_names_to_long_names}")


        # 2. Assign all long_name specified port infos to their associated ports
        long_name_port_infos = [port_info for port_info in port_infos if port_info.port is not None]
        identifiers_to_port_names = {}
        for port_info in long_name_port_infos:
            available_long_names = available_short_names_to_long_names.get(port_info.name, [])
            if port_info.long_name in available_long_names:
                available_long_names.remove(port_info.long_name)
                identifiers_to_port_names[port_info.identifier] = port_info.long_name
            else:
                identifiers_to_port_names[port_info.identifier] = None

        logger.debug(f"available_long_names after assigning long-named identifiers: {available_short_names_to_long_names}")

        # 3. Greedily assign remaining ports to short_name specified port infos
        short_name_port_infos = [port_info for port_info in port_infos if port_info.port is None]
        for port_info in short_name_port_infos:
            available_long_names = available_short_names_to_long_names.get(port_info.name, [])
            if available_long_names:
                long_name = available_long_names.pop()
                identifiers_to_port_names[port_info.identifier] = long_name
            else:
                identifiers_to_port_names[port_info.identifier] = None

        return identifiers_to_port_names

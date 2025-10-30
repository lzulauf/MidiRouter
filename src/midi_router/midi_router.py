import asyncio
import collections
from contextlib import contextmanager
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
        # Use a thread-safe queue for MIDI callbacks; we'll await it via
        # run_in_executor to avoid polling and remain event-driven.
        self.incoming_message_queue = queue.Queue()
        self._previous_identifiers_to_port_names = {}
        # Flag used to signal a requested config reload from another task
        self._config_changed = False
        # Current open port dicts and mappers (populated inside _prepare_run)
        self._current_input_ports_by_identifier = None
        self._current_output_ports_by_identifier = None
        self._current_mappers_by_input_port_name = None
        # Async lock to protect swapping mappers in-place
        self._mappers_lock = asyncio.Lock()

    def run(self):
        # Every time the midi devices change, re-initialize
        while True:
            try:
                with self._prepare_run() as mappers_by_input_port_name:
                    asyncio.run(self._run_async(mappers_by_input_port_name))
            except MidiDeviceChangeException:
                logger.warning("Midi Device Change Detected. Re-initializing")

    async def async_run(self):
        # Every time the midi devices change, re-initialize
        while True:
            try:
                with self._prepare_run() as mappers_by_input_port_name:
                    await self._run_async(mappers_by_input_port_name)
            except MidiDeviceChangeException:
                logger.warning("Midi Device Change Detected. Re-initializing")

    async def reload_config(self, new_config):
        """
        Replace the router configuration and request a graceful re-initialization
        of MIDI ports and mappers. This sets a flag that the running monitor loop
        will observe and raise MidiDeviceChangeException to trigger re-init.
        """
        self.config = new_config
        # Mark that a config change happened. The monitor loop will pick this up.
        self._config_changed = True

    # Backwards/alternative API name for hot-reload
    async def update_config(self, new_config):
        """Attempt to update the running router's configuration in-place.

        If the router currently has open ports (i.e. it's inside a run loop),
        this will rebuild the mappers using the existing open ports and swap
        them atomically so processing continues with the new mapping set.

        If there are no open ports, fall back to setting the reload flag which
        causes the run loop to re-initialize when it next checks devices.
        """
        # If currently running with open ports, rebuild mappers in-place
        if self._current_input_ports_by_identifier is not None and self._current_output_ports_by_identifier is not None:
            # Build new mappers from the new_config using existing ports
            logging.debug("MidiRouter: performing in-place config update")
            new_mappers = self._create_mappers_by_input_port_name(
                self._current_input_ports_by_identifier,
                self._current_output_ports_by_identifier,
                cfg=new_config,
            )
            async with self._mappers_lock:
                self.config = new_config
                self._current_mappers_by_input_port_name = new_mappers
        else:
            # Not presently running with open ports; mark for reload on next loop
            self.config = new_config
            self._config_changed = True
        return None

    @contextmanager
    def _prepare_run(self):
        input_port_names_by_identifier = self._get_identifiers_to_port_names(mido.get_input_names(), self.config.ports.inputs)
        output_port_names_by_identifier = self._get_identifiers_to_port_names(mido.get_output_names(), self.config.ports.outputs)


        input_ports_by_identifier = {}
        output_ports_by_identifier = {}
        try:
            for identifier, port_name in input_port_names_by_identifier.items():
                input_ports_by_identifier[identifier] = self._open_input_port(port_name)

            for identifier, port_name in output_port_names_by_identifier.items():
                output_ports_by_identifier[identifier] = self._open_output_port(port_name)

            # Expose the currently-open ports on the instance so callers (e.g. update_config)
            # can perform in-place updates without re-opening ports.
            self._current_input_ports_by_identifier = input_ports_by_identifier
            self._current_output_ports_by_identifier = output_ports_by_identifier

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

            yield mappers_by_input_port_name

        finally:
            # Wake up the message processing thread (if any) so it can exit when
            # ports are being closed or when the router is re-initializing.
            try:
                if self.incoming_message_queue is not None:
                    try:
                        self.incoming_message_queue.put_nowait(None)
                    except Exception:
                        # put_nowait may not exist on some queue-like objects; fall back
                        try:
                            self.incoming_message_queue.put(None)
                        except Exception:
                            pass
            except Exception:
                pass
            for port in itertools.chain(input_ports_by_identifier.values(), output_ports_by_identifier.values()):
                port.close()
            # Clear references to the ports so update_config knows ports are closed
            try:
                self._current_input_ports_by_identifier = None
                self._current_output_ports_by_identifier = None
                self._current_mappers_by_input_port_name = None
            except Exception:
                pass

    async def _run_async(self, mappers_by_input_port_name):
        # Store initial mappers for the running loop
        async with self._mappers_lock:
            self._current_mappers_by_input_port_name = mappers_by_input_port_name
        monitor_midi_device_change_task = asyncio.create_task(self._monitor_midi_device_changes())
        process_message_queue_task = asyncio.create_task(self._process_message_queue())
        try:
            # Wait until one of the tasks finishes (monitor will raise on change)
            await monitor_midi_device_change_task
            await process_message_queue_task
        except asyncio.CancelledError:
            # If cancelled, ensure background tasks are cancelled and awaited so
            # ports get closed in the _prepare_run finally block.
            for t in (monitor_midi_device_change_task, process_message_queue_task):
                if not t.done():
                    t.cancel()
            # Await both tasks to let them finish cancellation
            try:
                await asyncio.gather(monitor_midi_device_change_task, process_message_queue_task)
            except asyncio.CancelledError:
                # Expected; swallow to allow outer task cancellation to proceed
                pass
            raise

    async def _process_message_queue(self):
        """Process messages using a blocking get in a threadpool to avoid polling.

        This uses loop.run_in_executor(None, queue.get) which blocks a worker
        thread until a message arrives, then resumes the async loop.
        """
        loop = asyncio.get_running_loop()
        while True:
            try:
                incoming_message = await loop.run_in_executor(None, self.incoming_message_queue.get)
            except asyncio.CancelledError:
                break

            # TODO - what would cause this?
            # incoming_message may be None as a sentinel to indicate shutdown
            if incoming_message is None:
                break

            input_port_name, message = incoming_message
            logger.info(f"from {input_port_name}: {message}")
            # Read current mappers under lock to allow hot-swap
            async with self._mappers_lock:
                current = self._current_mappers_by_input_port_name or {}
            for mapper in current.get(input_port_name, []):
                mapper.send(input_port_name, message)
            logger.info("\n")

    async def _monitor_midi_device_changes(self):
        old_port_names = (mido.get_input_names(), mido.get_output_names())
        while True:
            # Check for explicit config change requests
            if self._config_changed:
                # reset flag and trigger re-initialization
                self._config_changed = False
                raise MidiDeviceChangeException()
            # Check for file-based reload request (created by CLI)
            import os
            reload_path = os.environ.get('MIDI_ROUTER_RELOAD_FILE', 'midi_reload.request')
            try:
                if os.path.exists(reload_path):
                    # Best-effort: remove the request file and trigger reload
                    try:
                        os.remove(reload_path)
                    except OSError as e:
                        logger.warning(f"Failed to remove reload request file {reload_path}: {e}")
                    logger.info(f"Detected reload request file {reload_path}")
                    raise MidiDeviceChangeException()
            except OSError as e:
                # If os.path.exists raised OSError (very unusual), log and continue
                logger.debug(f"Error checking reload file {reload_path}: {e}")
            new_port_names = (mido.get_input_names(), mido.get_output_names())
            if old_port_names != new_port_names:
                raise MidiDeviceChangeException()
            await asyncio.sleep(MIDI_DEVICE_CHANGE_CHECK_SLEEP)  # Cooperative parallelism plus wait

    def _create_mappers_by_input_port_name(self, input_ports_by_identifier, output_ports_by_identifier, cfg=None):
        """
        Generate mappers from input ports to output ports utilizing the mapper configuration.
        """
        # Allow callers to provide an alternative config (used during in-place updates)
        cfg = cfg or self.config

        mappers_by_input_port_name = {
            port.name: []
            for port in input_ports_by_identifier.values()
        }
        for mapping_config in cfg.mappings:
            mapper = Mapper.from_mapping_config(mapping_config, input_ports_by_identifier, output_ports_by_identifier)
            if mapping_config.from_port == config.PortConstant.ALL:
                for mapper_list in mappers_by_input_port_name.values():
                    mapper_list.append(mapper)
            else:
                # mapping may reference a device that's not currently connected
                # Try identifier-based lookup first; if that fails, fall back to
                # matching by port.name when available (tests use simple DummyPortInfo)
                port = None
                try:
                    spec_id = mapping_config.from_port.identifier
                    port = input_ports_by_identifier.get(spec_id)
                except Exception:
                    port = None

                if port is None:
                    # try to match by name if available
                    try:
                        spec_name = mapping_config.from_port.name
                    except Exception:
                        spec_name = None
                    if spec_name is not None:
                        for p in input_ports_by_identifier.values():
                            if getattr(p, 'name', None) == spec_name:
                                port = p
                                break

                if port is None:
                    # skip mappings for disconnected inputs
                    continue

                long_name = port.name
                mapper_list = mappers_by_input_port_name.get(long_name)
                # configs might reference disconnected devices, but mapper_lists only exist for connected
                # devices.
                if mapper_list is not None:
                    mapper_list.append(mapper)
        return mappers_by_input_port_name

    def _create_receive_message_callback(self, input_port_name):
        def _receive_message_callback(message):
            # Called from mido's background thread. Schedule a thread-safe put
            # into the asyncio queue so the async loop can process it.
            try:
                loop = getattr(self, '_run_loop', None)
                q = self.incoming_message_queue
                if loop is not None and q is not None:
                    loop.call_soon_threadsafe(q.put_nowait, IncomingMessage(input_port_name, message))
                else:
                    # Fallback to a blocking put if not running inside async loop
                    try:
                        self.incoming_message_queue.put(IncomingMessage(input_port_name, message))
                    except Exception:
                        pass
            except Exception:
                # Be defensive: don't allow the MIDI callback to raise
                logger.exception("Error enqueueing incoming MIDI message")
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
        self._previous_identifiers_to_port_names = dict(identifiers_to_port_names)
        # 3. Assign remaining port_infos (those without explicit long_name) by
        # matching their short name to available long names (pop the first match)
        remaining_port_infos = [port_info for port_info in port_infos if port_info.port is None]
        for port_info in remaining_port_infos:
            available_long_names = available_short_names_to_long_names.get(port_info.name, [])
            if available_long_names:
                chosen = available_long_names.pop(0)
                identifiers_to_port_names[port_info.identifier] = chosen
            else:
                # If exact short name not available, try to take any remaining long name
                fallback = None
                for short, longs in available_short_names_to_long_names.items():
                    if longs:
                        fallback = longs.pop(0)
                        break
                if fallback is not None:
                    identifiers_to_port_names[port_info.identifier] = fallback

        self._previous_identifiers_to_port_names = dict(identifiers_to_port_names)

        return identifiers_to_port_names

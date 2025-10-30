import asyncio
import pytest
import mido

from midi_router.midi_router import MidiRouter
from midi_router.config import ChannelConstant


class DummyPort:
    def __init__(self, name):
        self.name = name
        self.sent = []

    def send(self, message):
        self.sent.append(message)

    def close(self):
        pass


@pytest.mark.asyncio
async def test_event_queue_processing(monkeypatch):
    """Ensure the MIDI receive callback enqueues a message and mappers deliver it."""
    class DummyPortInfo:
        def __init__(self, identifier, name, port=None, long_name=None):
            self.identifier = identifier
            self.name = name
            self.port = port
            self.long_name = long_name

    class DummyPorts:
        def __init__(self):
            self.inputs = [DummyPortInfo('1', 'Input 1')]
            self.outputs = [DummyPortInfo('1', 'Output 1')]

    class DummyMapping:
        def __init__(self):
            self.from_port = DummyPortInfo('1', 'Input 1')
            self.to_port = DummyPortInfo('1', 'Output 1')
            self.from_channel = ChannelConstant.ALL
            self.to_channel = ChannelConstant.ALL

    class DummyConfig:
        def __init__(self):
            self.ports = DummyPorts()
            self.mappings = [DummyMapping()]

    cfg = DummyConfig()

    # Monkeypatch mido functions used by MidiRouter
    monkeypatch.setattr('midi_router.midi_router.mido.get_input_names', lambda: ["Input 1"])
    monkeypatch.setattr('midi_router.midi_router.mido.get_output_names', lambda: ["Output 1"])
    monkeypatch.setattr('midi_router.midi_router.mido.open_input', lambda name, callback=None: DummyPort(name))
    monkeypatch.setattr('midi_router.midi_router.mido.open_output', lambda name: DummyPort(name))

    router = MidiRouter(cfg)
    task = asyncio.create_task(router.async_run())
    await asyncio.sleep(0.05)

    # Craft a MIDI message and call the receive callback directly
    cb = router._create_receive_message_callback('Input 1')
    msg = mido.Message('note_on', note=60, velocity=64)

    # Call the callback which should enqueue the message; the router will process it
    cb(msg)
    await asyncio.sleep(0.05)

    # Inspect current mappers and ensure output port received the message
    async with router._mappers_lock:
        current = router._current_mappers_by_input_port_name or {}
    assert 'Input 1' in current
    mappers = current.get('Input 1', [])
    assert len(mappers) >= 1
    # The mapper should have at least one to_port; that to_port should have recorded the sent message
    sent_ports = [p for m in mappers for p in m.to_ports]
    assert any(getattr(p, 'sent', None) for p in sent_ports)
    assert any(msg in p.sent for p in sent_ports if hasattr(p, 'sent'))

    # Clean up
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

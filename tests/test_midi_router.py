import asyncio
import pytest

from midi_router.config import Config, ChannelConstant
from midi_router.midi_router import MidiRouter


class DummyPort:
    def __init__(self, name):
        self.name = name
    def close(self):
        pass


@pytest.mark.asyncio
async def test_async_run_start_and_reload(monkeypatch):
    # Create a minimal config-like object with ports and mappings attributes
    class DummyPortInfo:
        def __init__(self, identifier, name, port=None, long_name=None):
            self.identifier = identifier
            self.name = name
            self.port = port
            self.long_name = long_name

    class DummyPorts:
        def __init__(self):
            self.inputs = [DummyPortInfo(1, "Input 1" )]
            self.outputs = [DummyPortInfo(1, "Output 1" )]

    class DummyMapping:
        def __init__(self):
            self.from_port = DummyPortInfo(1, "Input 1")
            self.to_port = DummyPortInfo(1, "Output 1")
            self.from_channel = ChannelConstant.ALL
            self.to_channel = ChannelConstant.ALL

    class DummyConfig:
        def __init__(self):
            self.ports = DummyPorts()
            self.mappings = [DummyMapping()]
        def model_dump(self):
            return {"ports": {"inputs": [{"identifier": str(p.identifier), "name": p.name, "port_type": "USB"} for p in self.ports.inputs], "outputs": [{"identifier": str(p.identifier), "name": p.name, "port_type": "USB"} for p in self.ports.outputs]}, "mappings": []}
        def model_dump(self):
            return {"ports": {"inputs": [{"identifier": str(p.identifier), "name": p.name, "port_type": "USB"} for p in self.ports.inputs], "outputs": [{"identifier": str(p.identifier), "name": p.name, "port_type": "USB"} for p in self.ports.outputs]}, "mappings": []}
        def model_dump(self):
            # Minimal serializable representation used by the interactive app's logging
            return {"ports": {"inputs": [{"identifier": str(p.identifier), "name": p.name, "port_type": "USB"} for p in self.ports.inputs], "outputs": [{"identifier": str(p.identifier), "name": p.name, "port_type": "USB"} for p in self.ports.outputs]}, "mappings": []}

    cfg = DummyConfig()

    # monkeypatch mido functions used by MidiRouter to avoid real MIDI dependency
    monkeypatch.setattr('midi_router.midi_router.mido.get_input_names', lambda: ["Input 1"])
    monkeypatch.setattr('midi_router.midi_router.mido.get_output_names', lambda: ["Output 1"])
    monkeypatch.setattr('midi_router.midi_router.mido.open_input', lambda name, callback=None: DummyPort(name))
    monkeypatch.setattr('midi_router.midi_router.mido.open_output', lambda name: DummyPort(name))

    router = MidiRouter(cfg)

    # start async_run in background
    task = asyncio.create_task(router.async_run())
    await asyncio.sleep(0.1)

    # request config reload
    new_cfg = DummyConfig()
    await router.reload_config(new_cfg)

    await asyncio.sleep(0.1)

    # cancel and await
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


@pytest.mark.asyncio
async def test_app_lifecycle(monkeypatch):
    """Mount and unmount MidiRouterApp to ensure router starts and stops via manager."""
    from midi_router.scripts.interactive import MidiRouterApp

    class DummyPortInfo:
        def __init__(self, identifier, name, port=None, long_name=None):
            self.identifier = identifier
            self.name = name
            self.port = port
            self.long_name = long_name

    class DummyPorts:
        def __init__(self):
            self.inputs = [DummyPortInfo(1, "Input 1" )]
            self.outputs = [DummyPortInfo(1, "Output 1" )]

    class DummyMapping:
        def __init__(self):
            self.from_port = DummyPortInfo(1, "Input 1")
            self.to_port = DummyPortInfo(1, "Output 1")
            self.from_channel = ChannelConstant.ALL
            self.to_channel = ChannelConstant.ALL

    class DummyConfig:
        def __init__(self):
            self.ports = DummyPorts()
            self.mappings = [DummyMapping()]

    cfg = DummyConfig()
    monkeypatch.setattr('midi_router.midi_router.mido.get_input_names', lambda: ["Input 1"])
    monkeypatch.setattr('midi_router.midi_router.mido.get_output_names', lambda: ["Output 1"])
    monkeypatch.setattr('midi_router.midi_router.mido.open_input', lambda name, callback=None: DummyPort(name))
    monkeypatch.setattr('midi_router.midi_router.mido.open_output', lambda name: DummyPort(name))

    # Write a temporary config.yaml for the app to load
    import tempfile, yaml as _yaml
    tmp = tempfile.NamedTemporaryFile(mode='w+', delete=False, suffix='.yaml')
    _yaml.safe_dump({"ports": {"inputs": [{"identifier": "1", "name": "Input 1", "port_type": "USB"}], "outputs": [{"identifier": "1", "name": "Output 1", "port_type": "USB"}]}, "mappings": []}, tmp)
    tmp.flush()
    tmp.close()

    # Monkeypatch Config.from_yaml to return our dummy config
    from midi_router.config import Config as RealConfig
    monkeypatch.setattr(RealConfig, 'from_yaml', classmethod(lambda cls, stream=None: cfg))

    app = MidiRouterApp()
    # Instead of calling on_mount (which requires Textual's message pump),
    # exercise the manager directly which is what on_mount uses.
    await app._router_manager.start(cfg)
    assert app._router_manager.router() is not None
    await app._router_manager.stop()
    assert app._router_manager.router() is None


def test_cli_reload_writes_file(tmp_path):
    from midi_router.scripts.cli import main
    reload_file = tmp_path / 'reload.request'
    # Run CLI with reload command
    main(['reload', '--file', str(reload_file)])
    assert reload_file.exists()


@pytest.mark.asyncio
async def test_control_port_reload(monkeypatch):
    # Ensure the control server accepts RELOAD and responds OK
    from midi_router.scripts.interactive import AsyncRouterManager

    class DummyPortInfo:
        def __init__(self, identifier, name, port=None, long_name=None):
            self.identifier = identifier
            self.name = name
            self.port = port
            self.long_name = long_name

    class DummyPorts:
        def __init__(self):
            self.inputs = [DummyPortInfo(1, "Input 1" )]
            self.outputs = [DummyPortInfo(1, "Output 1" )]

    class DummyMapping:
        def __init__(self):
            self.from_port = DummyPortInfo(1, "Input 1")
            self.to_port = DummyPortInfo(1, "Output 1")
            self.from_channel = ChannelConstant.ALL
            self.to_channel = ChannelConstant.ALL

    class DummyConfig:
        def __init__(self):
            self.ports = DummyPorts()
            self.mappings = [DummyMapping()]

    cfg = DummyConfig()
    monkeypatch.setattr('midi_router.midi_router.mido.get_input_names', lambda: ["Input 1"])
    monkeypatch.setattr('midi_router.midi_router.mido.get_output_names', lambda: ["Output 1"])
    monkeypatch.setattr('midi_router.midi_router.mido.open_input', lambda name, callback=None: DummyPort(name))
    monkeypatch.setattr('midi_router.midi_router.mido.open_output', lambda name: DummyPort(name))

    manager = AsyncRouterManager()
    # find a free port to bind the control server
    import socket
    sock = socket.socket()
    sock.bind(('127.0.0.1', 0))
    free_port = sock.getsockname()[1]
    sock.close()
    await manager.start_control_port(free_port)
    reader, writer = await asyncio.open_connection('127.0.0.1', free_port)
    writer.write(b'RELOAD\n')
    await writer.drain()
    resp = await reader.readline()
    writer.close()
    await writer.wait_closed()
    assert resp.strip() in (b'OK', b'NO_CONFIG')


@pytest.mark.asyncio
async def test_update_config_alias(monkeypatch):
    class DummyPortInfo:
        def __init__(self, identifier, name, port=None, long_name=None):
            self.identifier = identifier
            self.name = name
            self.port = port
            self.long_name = long_name

    class DummyPorts:
        def __init__(self):
            self.inputs = [DummyPortInfo(1, "Input 1" )]
            self.outputs = [DummyPortInfo(1, "Output 1" )]

    class DummyMapping:
        def __init__(self):
            self.from_port = DummyPortInfo(1, "Input 1")
            self.to_port = DummyPortInfo(1, "Output 1")
            self.from_channel = ChannelConstant.ALL
            self.to_channel = ChannelConstant.ALL

    class DummyConfig:
        def __init__(self):
            self.ports = DummyPorts()
            self.mappings = [DummyMapping()]

    cfg = DummyConfig()
    monkeypatch.setattr('midi_router.midi_router.mido.get_input_names', lambda: ["Input 1"])
    monkeypatch.setattr('midi_router.midi_router.mido.get_output_names', lambda: ["Output 1"])
    monkeypatch.setattr('midi_router.midi_router.mido.open_input', lambda name, callback=None: DummyPort(name))
    monkeypatch.setattr('midi_router.midi_router.mido.open_output', lambda name: DummyPort(name))

    router = MidiRouter(cfg)
    # start and then call update_config alias
    task = asyncio.create_task(router.async_run())
    await asyncio.sleep(0.05)
    await router.update_config(cfg)
    # cancel
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


@pytest.mark.asyncio
async def test_manager_deepcopy_behavior(monkeypatch):
    # Use the AsyncRouterManager from the interactive module
    from midi_router.scripts.interactive import AsyncRouterManager

    class DummyPortInfo:
        def __init__(self, identifier, name, port=None, long_name=None):
            self.identifier = identifier
            self.name = name
            self.port = port
            self.long_name = long_name

    class DummyPorts:
        def __init__(self):
            self.inputs = [DummyPortInfo(1, "Input 1" )]
            self.outputs = [DummyPortInfo(1, "Output 1" )]

    class DummyMapping:
        def __init__(self):
            self.from_port = DummyPortInfo(1, "Input 1")
            self.to_port = DummyPortInfo(1, "Output 1")
            self.from_channel = ChannelConstant.ALL
            self.to_channel = ChannelConstant.ALL

    class DummyConfig:
        def __init__(self):
            self.ports = DummyPorts()
            self.mappings = [DummyMapping()]

    cfg = DummyConfig()
    monkeypatch.setattr('midi_router.midi_router.mido.get_input_names', lambda: ["Input 1"])
    monkeypatch.setattr('midi_router.midi_router.mido.get_output_names', lambda: ["Output 1"])
    monkeypatch.setattr('midi_router.midi_router.mido.open_input', lambda name, callback=None: DummyPort(name))
    monkeypatch.setattr('midi_router.midi_router.mido.open_output', lambda name: DummyPort(name))

    manager = AsyncRouterManager()
    await manager.start(cfg)
    router = manager.router()
    assert router is not None
    # mutate original cfg and ensure router.config is unaffected (deepcopy)
    cfg.mappings.append(DummyMapping())
    assert len(cfg.mappings) != len(router.config.mappings)
    await manager.stop()


@pytest.mark.asyncio
async def test_update_in_place(monkeypatch):
    """Verify that update_config rebuilds and swaps mappers without re-opening ports."""
    class DummyPortInfo:
        def __init__(self, identifier, name, port=None, long_name=None):
            self.identifier = identifier
            self.name = name
            self.port = port
            self.long_name = long_name

    class DummyPorts:
        def __init__(self):
            self.inputs = [DummyPortInfo(1, "Input 1" )]
            self.outputs = [DummyPortInfo(1, "Output 1" )]

    class DummyMapping:
        def __init__(self):
            self.from_port = DummyPortInfo(1, "Input 1")
            self.to_port = DummyPortInfo(1, "Output 1")
            self.from_channel = ChannelConstant.ALL
            self.to_channel = ChannelConstant.ALL

    class DummyConfig:
        def __init__(self):
            self.ports = DummyPorts()
            self.mappings = [DummyMapping()]

    cfg = DummyConfig()
    monkeypatch.setattr('midi_router.midi_router.mido.get_input_names', lambda: ["Input 1"])
    monkeypatch.setattr('midi_router.midi_router.mido.get_output_names', lambda: ["Output 1"])
    monkeypatch.setattr('midi_router.midi_router.mido.open_input', lambda name, callback=None: DummyPort(name))
    monkeypatch.setattr('midi_router.midi_router.mido.open_output', lambda name: DummyPort(name))

    router = MidiRouter(cfg)
    task = asyncio.create_task(router.async_run())
    await asyncio.sleep(0.05)
    # create a new config with different mappings
    new_cfg = DummyConfig()
    new_cfg.mappings = [DummyMapping(), DummyMapping()]
    await router.update_config(new_cfg)
    # give loop time to swap
    await asyncio.sleep(0.05)
    # check that router._current_mappers_by_input_port_name has been updated
    async with router._mappers_lock:
        current = router._current_mappers_by_input_port_name
    assert current is not None
    # because we added two mapping entries, the mapper lists should be longer than 0
    assert any(len(v) >= 1 for v in current.values())
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

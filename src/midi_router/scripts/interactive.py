# MIDI Router Interactive Script
#
# Running
#   $ midi-router-interactive
#
# Debugging
# 1. Start dev console
#   $ textual console
# 2. Start in dev mode (needs python function that returns app to run)
#   $ textual run --dev midi_router.scripts.interactive:app
#
# Serving (needs program to run)
#   $ textual serve --dev midi-router-interactive
import logging
import asyncio
from typing import Optional

from rich.logging import RichHandler
from textual.app import App
from textual.containers import Center, Horizontal, Vertical, CenterMiddle
from textual.logging import TextualHandler
from textual.reactive import reactive
from textual.screen import ModalScreen, Screen
from textual.widget import Widget
from textual.widgets import Button, Header, Footer, Label, ListItem, ListView, RichLog
import yaml

from midi_router.config import Config, Mapping, PortSpecifier, ChannelConstant
from midi_router.midi_router import MidiRouter
from dataclasses import dataclass
from typing import Optional as _Optional


@dataclass
class RouterEvent:
    event: str
    timestamp: float
    mapping_count: int | None = None
    inputs: list[str] | None = None
    outputs: list[str] | None = None


class RichLogConsole(RichLog):
    """
    Extend RichLog with API for Rich Consoles.

    Implements the 'file' attribute and print functions to match Console class
    expected by RichHandler.
    """
    file = False
    print = RichLog.write


rich_log = RichLogConsole(id="log-view")
logging.basicConfig(
    level=logging.DEBUG,
    handlers=[
        TextualHandler(),  # Enable dev console logging
        RichHandler(console=rich_log, show_time=False)  # Enable logging to widget
    ]
)

class MappingListItem(ListItem):
    mapping: reactive[Mapping] = reactive(None, recompose=False)

    def __init__(self, mapping):
        super().__init__()
        self.mapping = mapping

    def compose(self):
        yield Label(f"Route from {self.mapping.from_port} to {self.mapping.to_port}")


class MappingListView(ListView):
    BINDINGS = [
        ("enter", "popup_editor", "Edit Mapping"),
    ]

    midi_router: reactive[MidiRouter|None] = reactive(None, recompose=False)
    mappings: reactive[list[Mapping]] = reactive([], recompose=False)

    def __init__(self, mappings: list[Mapping] = None):
        super().__init__()
        self.mappings = mappings or []

    def compose(self):
        yield from (MappingListItem(mapping=mapping) for mapping in self.mappings)
        yield ListItem(Center(Button("Add Mapping", id="add-mapping-btn")))

    async def on_button_pressed(self, event):
        pass

    async def action_popup_editor(self):
        logging.debug(f"Popup editor for mapping: {self.highlighted_child}")
        # If the highlighted child is the Add Mapping row (last row), open the add-mapping screen
        if self.index == len(self.mappings):
            await self.run_action("app.push_screen('add-mapping')")
            return
        await self.run_action(f"app.set_active_mapping_index({self.index})")
        await self.run_action("app.push_screen('mapping-editor')")

class Routes(Widget):
    """Render the current configuration's routes."""
    midi_router: reactive[MidiRouter|None] = reactive(None, recompose=True)

    def compose(self):
        # Create a MappingListView and bind it to this Routes' midi_router so it
        # can update its mappings reactively when the router changes.
        mv = MappingListView(self.midi_router.config.mappings if self.midi_router else [])
        mv.data_bind(Routes.midi_router)
        yield mv.focus()

    def on_mount(self):
        logging.debug(f"Routes widget mounted with midi_router: {self.midi_router}")
        #self.query_one(MappingListView).focus()


class MainScreen(Screen):
    midi_router: reactive[MidiRouter|None] = reactive(None, recompose=False)

    def compose(self):

        yield Header()
        with Horizontal():
            yield Routes(id="routes-view").data_bind(MainScreen.midi_router)
            with Vertical():
                # Router status widget (small) shown above the log
                yield rich_log
                yield RouterStatus(id="router-status").data_bind(MainScreen.midi_router)
                yield Label("This is a placeholder for the interactive MIDI router interface.", expand=True)
        yield Footer()

    def on_mount(self):
        self.title = "MIDI Router"
        self.sub_title = "Manage your MIDI routing interactively"
        logging.debug(f"MainScreen mounted with midi_router: {self.midi_router}")


class MappingEditor(ModalScreen):
    """Screen to edit a Mapping."""
    BINDINGS = [
        ("escape", "app.pop_screen", "Close Editor"),
    ]
    midi_router: reactive[MidiRouter|None] = reactive(None, recompose=False)
    active_mapping_index: reactive[int] = reactive(0, recompose=False)

    def compose(self):
        yield Header()
        with CenterMiddle():
            if self.midi_router:
                mapping = self.midi_router.config.mappings[self.active_mapping_index]
                yield Label(f"Editing mapping from {mapping.from_port} to {mapping.to_port}")
            else:
                yield Label(f"No Midi Router available.")
        yield Footer()

    def on_mount(self):
        self.title = "MIDI Router"
        self.sub_title = "Edit Mapping"


class AddMappingScreen(ModalScreen):
    """Modal screen to add a new mapping using existing ports from the current config."""
    BINDINGS = [
        ("escape", "app.pop_screen", "Close"),
    ]
    midi_router: reactive[MidiRouter|None] = reactive(None, recompose=False)

    def compose(self):
        yield Header()
        with CenterMiddle():
            if self.midi_router is None:
                yield Label("No router available to add mapping to.")
            else:
                cfg = self.midi_router.config
                # Build selection lists from cfg.ports if available
                inputs = []
                outputs = []
                try:
                    inputs = [p.name for p in cfg.ports.inputs]
                except Exception:
                    inputs = []
                try:
                    outputs = [p.name for p in cfg.ports.outputs]
                except Exception:
                    outputs = []
                yield Label("Select input port:")
                for name in inputs:
                    yield Button(name, id=f"from:{name}")
                yield Label("Select output port:")
                for name in outputs:
                    yield Button(name, id=f"to:{name}")
                yield Button("Apply", id="apply-mapping")
                yield Button("Cancel", id="cancel-mapping")
        yield Footer()

    def on_mount(self):
        # Ensure the screen has a midi_router reference. Prefer the app's router,
        # fall back to the manager's pending config (wrapped) or loading config.yaml.
        if self.midi_router is not None:
            return
        mr = getattr(self.app, 'midi_router', None)
        if mr is not None:
            self.midi_router = mr
            return
        # Try pending config from manager
        cfg = None
        try:
            cfg = self.app.router_manager.pending_config
        except Exception:
            cfg = None

        if cfg is None:
            cfg = Config.from_yaml(stream=open('config.yaml'))
        if cfg is not None:
            from types import SimpleNamespace
            self.midi_router = SimpleNamespace(config=cfg)

    async def on_button_pressed(self, event):
        sender = None
        try:
            sender = event.button
        except AttributeError:
            try:
                sender = event.sender
            except AttributeError:
                sender = None
        if not sender:
            return
        sid = getattr(sender, 'id', None)
        if sid is None:
            return
        # maintain selection state on the screen instance
        sel_from = getattr(self, '_sel_from', None)
        sel_to = getattr(self, '_sel_to', None)
        if sid.startswith('from:'):
            self._sel_from = sid.split(':', 1)[1]
            # feedback: set button label or log
            logging.debug(f"Selected from: {self._sel_from}")
            return
        if sid.startswith('to:'):
            self._sel_to = sid.split(':', 1)[1]
            logging.debug(f"Selected to: {self._sel_to}")
            return
        if sid == 'cancel-mapping':
            await self.app.pop_screen()
            return
        if sid == 'apply-mapping':
            # Ensure selections exist
            from_name = getattr(self, '_sel_from', None)
            to_name = getattr(self, '_sel_to', None)
            if not from_name or not to_name:
                logging.debug("Both from and to ports must be selected to add a mapping")
                return
            # Create a new Mapping object and append to a copy of current config then apply
            try:
                cfg = self.midi_router.config
            except Exception:
                cfg = None
            if cfg is None:
                logging.debug("No config available to update")
                return
            # Build new mapping specifiers using PortSpecifier (identifier is name here for simplicity)
            new_mapping = Mapping(from_port=PortSpecifier(identifier=str(from_name)), to_port=PortSpecifier(identifier=str(to_name)), from_channel=ChannelConstant.ALL, to_channel=ChannelConstant.ALL)
            # Append to a shallow copy of config (try to preserve model structure)
            try:
                import copy
                new_cfg = copy.deepcopy(cfg)
                new_cfg.mappings = list(new_cfg.mappings or []) + [new_mapping]
            except Exception:
                # Fallback: build a minimal config-ish object
                class _TmpCfg:
                    def __init__(self, ports, mappings):
                        self.ports = ports
                        self.mappings = mappings
                new_cfg = _TmpCfg(getattr(cfg, 'ports', None), list(getattr(cfg, 'mappings', [])) + [new_mapping])

            # Ask the app to apply the new config
            await self.app.action_apply_config(new_cfg)
            # Close the modal
            await self.app.pop_screen()



class RouterStatus(Widget):
    """Small status widget showing router running state, ports, counts and reload button."""
    # allow data binding from MainScreen.midi_router
    midi_router: reactive[MidiRouter|None] = reactive(None, recompose=False)
    running: reactive[bool] = reactive(False, recompose=False)
    last_started: reactive[str] = reactive("Never", recompose=False)
    last_reloaded: reactive[str] = reactive("Never", recompose=False)
    mapping_count: reactive[int] = reactive(0, recompose=False)
    inputs: reactive[str] = reactive("None", recompose=False)
    outputs: reactive[str] = reactive("None", recompose=False)

    def on_mount(self) -> None:
        # Register with AsyncRouterManager to receive events instead of polling
        mgr = self.app.router_manager
        mgr.register_listener(self._on_manager_event)
        # Immediately refresh status so the widget reflects the current router
        # state (manager may have started the router before this widget mounted).
        try:
            self._refresh_status()
        except Exception:
            # don't fail mount if refresh has issues
            logging.debug('RouterStatus: initial refresh failed', exc_info=True)

    def on_unmount(self) -> None:
        mgr = self.app.router_manager
        mgr.unregister_listener(self._on_manager_event)

    async def _on_manager_event(self, event: RouterEvent):
        """Called by AsyncRouterManager when start/stop/reload occurs.

        `event` is a RouterEvent dataclass instance.
        """
        name = event.event
        ts = event.timestamp

        if name == "started":
            if ts:
                import time as _time
                self.last_started = _time.strftime("%Y-%m-%d %H:%M:%S", _time.localtime(ts))
            self.running = True
        elif name == "reloaded":
            if ts:
                import time as _time
                self.last_reloaded = _time.strftime("%Y-%m-%d %H:%M:%S", _time.localtime(ts))
        elif name == "stopped":
            # clear running flags
            self.running = False

        # If event contains mapping/port info, use it to avoid extra introspection
        if event.mapping_count is not None:
            self.mapping_count = event.mapping_count
        if event.inputs is not None:
            self.inputs = ", ".join(event.inputs) if event.inputs else "None"
        if event.outputs is not None:
            self.outputs = ", ".join(event.outputs) if event.outputs else "None"

        # refresh the rest of the state (mapping count, ports) from manager/router
        await self.refresh_now()

    def _refresh_status(self) -> None:
        mgr = self.app.router_manager
        running = bool(mgr and mgr.router)
        self.running = running
        if mgr:
            if mgr.last_started_at:
                import time as _time
                self.last_started = _time.strftime("%Y-%m-%d %H:%M:%S", _time.localtime(mgr.last_started_at))
            else:
                self.last_started = "Never"
            if mgr.last_reloaded_at:
                import time as _time
                self.last_reloaded = _time.strftime("%Y-%m-%d %H:%M:%S", _time.localtime(mgr.last_reloaded_at))
            else:
                self.last_reloaded = "Never"
            router = mgr.router
        else:
            self.last_started = "Never"
            self.last_reloaded = "Never"
            router = None

        # mapping count and port lists (best-effort)
            if router is not None:
                try:
                    cfg = router.config
                except Exception:
                    cfg = None
                if cfg:
                    self.mapping_count = len(cfg.mappings or [])
                    # try to infer ports from router if available, otherwise from config mappings
                    inputs_list = []
                    outputs_list = []
                    # try direct attribute access for input_ports/output_ports
                    try:
                        inputs_list = [p.name for p in router.input_ports]
                    except Exception:
                        inputs_list = []
                    if not inputs_list:
                        try:
                            inputs_list = sorted({m.from_port for m in cfg.mappings})
                        except (AttributeError, TypeError, KeyError):
                            inputs_list = []
                    try:
                        outputs_list = [p.name for p in router.output_ports]
                    except Exception:
                        outputs_list = []
                    if not outputs_list:
                        try:
                            outputs_list = sorted({m.to_port for m in cfg.mappings})
                        except (AttributeError, TypeError, KeyError):
                            outputs_list = []
                    self.inputs = ", ".join(inputs_list) if inputs_list else "None"
                    self.outputs = ", ".join(outputs_list) if outputs_list else "None"
            else:
                self.mapping_count = 0
                self.inputs = "None"
                self.outputs = "None"

        # force a redraw
        self.refresh()

    async def refresh_now(self) -> None:
        """Coroutine to refresh state immediately (useful after actions)."""
        # run the same code synchronously to update reactive fields
        self._refresh_status()

    def watch_running(self, running: bool) -> None:
        """Update the Start/Stop button label whenever the running state changes.

        Textual Button APIs differ between versions; try `set_label()` first,
        otherwise set the `label` attribute directly.
        """
        try:
            btn = self.query_one('#startstop-btn', expect_type=None)
        except Exception:
            btn = None
        if btn is None:
            return
        new_label = 'Stop' if running else 'Start'
        try:
            # some Textual versions provide set_label
            btn.set_label(new_label)
        except Exception:
            try:
                btn.label = new_label
            except Exception:
                # last resort: update the button's renderable text if available
                try:
                    btn.update(new_label)
                except Exception:
                    pass

    def compose(self):
        yield Label(f"Router running: {'Yes' if self.running else 'No'}")
        yield Label(f"Mappings: {self.mapping_count}")
        yield Label(f"Inputs: {self.inputs}")
        yield Label(f"Outputs: {self.outputs}")
        yield Label(f"Last started: {self.last_started}")
        yield Label(f"Last reloaded: {self.last_reloaded}")
        # Start/Stop button label depends on running state
        yield Button("Stop" if self.running else "Start", id="startstop-btn")
        yield Button("Reload", id="reload-btn")

    async def on_button_pressed(self, event):
        # support different event shapes across Textual versions
        sender = None
        try:
            sender = event.button
        except AttributeError:
            try:
                sender = event.sender
            except AttributeError:
                sender = None
        if not sender:
            return
        try:
            sid = sender.id
        except AttributeError:
            sid = None
        if sid == "reload-btn":
            # call app action to reload; use debounce/start path
            try:
                await self.app.action_reload_router()
            except AttributeError:
                # App may not implement reload action in some test harnesses
                pass
            # update immediately (allow errors to propagate so tests detect them)
            await self.refresh_now()
        elif sid == "startstop-btn":
            # start or stop the router via the manager
            mgr = self.app.router_manager
            if mgr is None:
                return
            if mgr.router is None:
                # attempt to start using the current app config if possible
                cfg = None
                # if app has a loaded config through midi_router, use it
                if self.app.midi_router is not None:
                    try:
                        cfg = self.app.midi_router.config
                    except Exception:
                        cfg = None
                else:
                    # try to load from config.yaml as on_mount does
                    try:
                        cfg = Config.from_yaml(stream=open("config.yaml"))
                    except (FileNotFoundError, yaml.YAMLError) as e:
                        logging.debug(f"Could not load config.yaml: {e}")
                        cfg = None
                if cfg is not None:
                    await mgr.start(cfg)
                    # update the app binding
                    self.app.midi_router = mgr.router
                    # immediate refresh
                    await self.refresh_now()
            else:
                await mgr.stop()
                self.app.midi_router = None
                await self.refresh_now()


# New: AsyncRouterManager to own MidiRouter instance + task
class AsyncRouterManager:
    """
    Owns a MidiRouter instance and its asyncio.Task.
    Start/stop the router from an async context.
    """
    def __init__(self, debounce_delay: float = 0.05):
        self._router: Optional[MidiRouter] = None
        self._task: Optional[asyncio.Task] = None
        self._lock = asyncio.Lock()
        # Debounce helpers
        self._debounce_delay = debounce_delay
        self._pending_config: Optional[Config] = None
        self._pending_start_task: Optional[asyncio.Task] = None
        self._pending_futures: list[asyncio.Future] = []
        # Control server task and port
        self._control_server_task: Optional[asyncio.Task] = None
        self._control_port: Optional[int] = None
        # timestamps
        self.last_started_at: Optional[float] = None
        self.last_reloaded_at: Optional[float] = None
        # event listeners: callables/coroutines that accept an event name
        self._listeners = set()

    @property
    def router(self) -> Optional[MidiRouter]:
        return self._router

    @property
    def debounce_delay(self) -> float:
        return self._debounce_delay

    @debounce_delay.setter
    def debounce_delay(self, v: float):
        self._debounce_delay = v
    
    @property
    def pending_config(self) -> Optional[Config]:
        return self._pending_config

    async def start(self, config: Config):
        """
        Debounced start: coalesce rapid start requests and return when the
        router instance is started. Callers await the router instance.
        """
        # store the latest pending config
        self._pending_config = config
        loop = asyncio.get_running_loop()
        fut = loop.create_future()
        self._pending_futures.append(fut)
        # schedule a debounced start if not already pending
        if self._pending_start_task is None or self._pending_start_task.done():
            self._pending_start_task = asyncio.create_task(self._debounced_start())
        return await fut

    async def _debounced_start(self):
        await asyncio.sleep(self._debounce_delay)
        async with self._lock:
            await self._stop_unlocked()
            import copy
            cfg_copy = copy.deepcopy(self._pending_config)
            logging.debug("AsyncRouterManager: starting router")
            self._router = MidiRouter(cfg_copy)
            try:
                self._task = asyncio.create_task(self._router.async_run())
            except AttributeError:
                # Router may not implement async_run in some test fakes
                self._task = None
            # record start time
            import time
            self.last_started_at = time.time()
            # compute snapshot info for event payloads (mapping count, ports)
            mapping_count = None
            inputs = None
            outputs = None
            try:
                if self._router is not None:
                    try:
                        mapping_count = len(self._router.config.mappings or [])
                    except Exception:
                        mapping_count = None
                    try:
                        inputs = [p.name for p in getattr(self._router, 'input_ports', [])]
                    except Exception:
                        inputs = None
                    try:
                        outputs = [p.name for p in getattr(self._router, 'output_ports', [])]
                    except Exception:
                        outputs = None
            except Exception:
                mapping_count = None
                inputs = None
                outputs = None

            # notify listeners that a start occurred with a RouterEvent
            evt = RouterEvent(event="started", timestamp=self.last_started_at, mapping_count=mapping_count, inputs=inputs, outputs=outputs)
            await self._notify_listeners(evt)
            # resolve pending futures
            for fut in self._pending_futures:
                if not fut.done():
                    fut.set_result(self._router)
            self._pending_futures.clear()

    async def _stop_unlocked(self):
        if self._task:
            logging.debug("AsyncRouterManager: stopping router task")
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        # compute snapshot before clearing router
        mapping_count = None
        inputs = None
        outputs = None
        try:
            if self._router is not None:
                try:
                    mapping_count = len(self._router.config.mappings or [])
                except Exception:
                    mapping_count = None
                try:
                    inputs = [p.name for p in getattr(self._router, 'input_ports', [])]
                except Exception:
                    inputs = None
                try:
                    outputs = [p.name for p in getattr(self._router, 'output_ports', [])]
                except Exception:
                    outputs = None
        except Exception:
            mapping_count = None
            inputs = None
            outputs = None

        self._router = None
        # notify listeners about stop with timestamp and snapshot
        import time
        evt = RouterEvent(event="stopped", timestamp=time.time(), mapping_count=mapping_count, inputs=inputs, outputs=outputs)
        await self._notify_listeners(evt)

    async def start_control_port(self, port: int):
        """Start a simple TCP control server that accepts a single-line command 'RELOAD'."""
        if self._control_server_task and not self._control_server_task.done():
            return
        self._control_port = port
        self._control_server_task = asyncio.create_task(self._run_control_server(port))

    async def _run_control_server(self, port: int):
        server = await asyncio.start_server(self._handle_control_conn, '127.0.0.1', port)
        async with server:
            await server.serve_forever()

    async def _handle_control_conn(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        try:
            data = await reader.readline()
            cmd = data.decode().strip().upper()
            if cmd == 'RELOAD':
                # trigger reload using the last pending or current config
                config = self._pending_config or (self._router.config if self._router else None)
                if config is not None:
                    await self.start(config)
                    import time
                    self.last_reloaded_at = time.time()
                    # compute snapshot info for reload event
                    mapping_count = None
                    inputs = None
                    outputs = None
                    try:
                        # prefer pending config if router not available yet
                        cfg = self._pending_config or (self._router.config if self._router else None)
                        if cfg is not None:
                            try:
                                mapping_count = len(cfg.mappings or [])
                            except Exception:
                                mapping_count = None
                        if self._router is not None:
                            try:
                                inputs = [p.name for p in getattr(self._router, 'input_ports', [])]
                            except Exception:
                                inputs = None
                            try:
                                outputs = [p.name for p in getattr(self._router, 'output_ports', [])]
                            except Exception:
                                outputs = None
                    except Exception:
                        mapping_count = None
                        inputs = None
                        outputs = None

                    # notify listeners about reload with timestamp and snapshot
                    evt = RouterEvent(event="reloaded", timestamp=self.last_reloaded_at, mapping_count=mapping_count, inputs=inputs, outputs=outputs)
                    await self._notify_listeners(evt)
                    writer.write(b'OK\n')
                else:
                    writer.write(b'NO_CONFIG\n')
            else:
                writer.write(b'UNKNOWN\n')
            await writer.drain()
        except (asyncio.IncompleteReadError, ConnectionResetError, UnicodeDecodeError) as e:
            logging.debug(f"Control connection error: {e}")
        finally:
            try:
                writer.close()
                await writer.wait_closed()
            except (ConnectionResetError, RuntimeError) as e:
                logging.debug(f"Error closing control connection: {e}")

    def register_listener(self, listener):
        """Register a callable or coroutine that accepts a single event string."""
        # let unhashable listeners raise TypeError — that's a programmer error
        self._listeners.add(listener)

    def unregister_listener(self, listener):
        self._listeners.discard(listener)

    async def _notify_listeners(self, payload: RouterEvent):
        """Notify registered listeners with a RouterEvent instance.

        Listeners receive a single RouterEvent argument. Listener callables
        may be sync or async; async results are awaited concurrently. Listener
        exceptions are returned by `asyncio.gather` and do not stop other
        listeners from executing.
        """
        if not isinstance(payload, RouterEvent):
            raise TypeError("_notify_listeners requires a RouterEvent instance")
        coros = []
        for l in list(self._listeners):
            res = l(payload)
            if asyncio.iscoroutine(res):
                coros.append(res)
        if coros:
            await asyncio.gather(*coros, return_exceptions=True)

    async def stop(self):
        async with self._lock:
            await self._stop_unlocked()


class MidiRouterApp(App):
    CSS_PATH = "midi-router-interactive.tcss"
    BINDINGS = [
        ("r", "reload_router", "Reload Router"),
    ]
    #SCREENS = {'mapping-editor': MappingEditor}

    midi_router: reactive[MidiRouter|None] = reactive(None, recompose=False)
    active_mapping_index: reactive[int] = reactive(0, recompose=False)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._router_manager = AsyncRouterManager()

    @property
    def router_manager(self) -> AsyncRouterManager:
        return self._router_manager

    @property
    def debounce_delay(self) -> float:
        return self._router_manager.debounce_delay

    @debounce_delay.setter
    def debounce_delay(self, v: float):
        self._router_manager.debounce_delay = v

    async def action_reload_router(self):
        """Reload the currently-loaded router configuration (graceful restart)."""
        if self.midi_router is None:
            logging.debug("No midi_router available to reload")
            return
        # Use manager.start to restart with the current config (manager handles debounce)
        await self._router_manager.start(self.midi_router.config)

    async def on_mount(self):
        # Load config and start router in background, keep router for UI binding
        config = Config.from_yaml(stream=open("config.yaml"))
        await self._router_manager.start(config)
        self.midi_router = self._router_manager.router

        # Safely attempt to dump the router config for debug logging. Some tests
        # use simple dummy config objects that may not implement `model_dump()`.
        cfg_dump = {}
        if self.midi_router is not None:
            try:
                cfg_obj = self.midi_router.config
            except Exception:
                cfg_obj = None
            if cfg_obj is not None:
                try:
                    cfg_dump = cfg_obj.model_dump()
                except (AttributeError, TypeError, ValueError):
                    logging.debug("model_dump() failed for cfg_obj")
                    try:
                        cfg_dump = cfg_obj.__dict__
                    except Exception:
                        cfg_dump = repr(cfg_obj)
        logging.debug(f"App Mounted with config: {yaml.dump(cfg_dump)}")
        main_screen = MainScreen()
        main_screen.data_bind(MidiRouterApp.midi_router)
        editor_screen = MappingEditor()
        editor_screen.data_bind(MidiRouterApp.midi_router)
        editor_screen.data_bind(MidiRouterApp.active_mapping_index)
        add_screen = AddMappingScreen()
        add_screen.data_bind(MidiRouterApp.midi_router)
        self.install_screen(main_screen, name="main")
        self.install_screen(editor_screen, name="mapping-editor")
        self.install_screen(add_screen, name='add-mapping')
        self.push_screen("main")

    async def on_unmount(self):
        await self._router_manager.stop()


    def action_set_active_mapping_index(self, index: int):
        self.active_mapping_index = index
        logging.debug(f"Set active mapping index: {self.active_mapping_index}")

    async def action_apply_config(self, new_config: Config):
        """
        Apply a new configuration from the UI.
        This restarts the running MidiRouter with the provided config.
        """
        await self._router_manager.start(new_config)
        # update UI binding to point at the new router instance
        self.midi_router = self._router_manager.router



def app():
    """
    Return the App.
    
    Used by `textual run` to start the app.
    """
    return MidiRouterApp()

def main():
    """
    Run the App.
    """
    app().run()


if __name__ == "__main__":
    main()

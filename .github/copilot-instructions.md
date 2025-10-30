<!--
Guidance for AI coding agents working on the MidiRouter repository.
Keep this file short and pragmatic. Only include patterns and decisions that are
discoverable from the codebase.
-->

# MidiRouter — Agent Instructions

Purpose: help an AI agent be productive immediately when making changes to
the MidiRouter project (Python, textual UI, async runtime).

Key files to read first
- `src/midi_router/midi_router.py` — core async router: opens ports, maps messages,
  and exposes `async_run()`, `update_config()` and `reload_config()` semantics.
- `src/midi_router/scripts/interactive.py` — Textual UI and `AsyncRouterManager`.
  This file demonstrates how the UI and router are orchestrated (manager owns router
  tasks, supports debounce and control-port, and now supports listener callbacks).
- `src/midi_router/config.py` — config model used across the app (ports, mappings).
- `src/midi_router/mapper.py` — mapping logic used by the router (how messages are transformed).

Big-picture architecture
- Single Python package `midi_router` (src/ layout). Runtime components:
  - MidiRouter: background async service that interfaces with `mido` (MIDI I/O).
  - AsyncRouterManager: UI-friendly orchestrator that starts/stops the router in an
    asyncio.Task, debounces rapid starts, and exposes a small TCP control server.
  - Textual UI (`MidiRouterApp`): uses the manager to start/stop/reload and binds
    to the currently-running router for rendering mappings.
- Dataflow: Config -> Manager (deepcopy on start) -> MidiRouter -> mido ports -> mapping
  functions. UI modifies or supplies a new Config and calls manager.start(config).

Developer workflows & commands
- Tests: pytest + pytest-asyncio. Run from repo root using the project's venv:
  ```powershell
  .venv\Scripts\python.exe -m pytest -q
  ```
- Run interactive UI in dev mode with Textual (project should be importable):
  ```powershell
  textual run --dev midi_router.scripts.interactive:app
  # or
  midi-router-interactive  # if entry point installed
  ```
- Packaging / editable install uses `pyproject.toml` with a src layout. Use pip editable
  installs if you need local iteration:
  ```powershell
  .venv\Scripts\python.exe -m pip install -e .
  ```

Project-specific conventions
- `AsyncRouterManager` is authoritative for starting/stopping router instances.
  Always start/stop via manager in async contexts; do not directly `create_task(router.async_run())`
  in UI code. The manager deep-copies config before starting to avoid shared-state races.
- UI code treats the running router as read-only: replace the router via `manager.start(new_cfg)`
  rather than mutating fields inside an active `MidiRouter` unless the router exposes
  a specific `update_config()` API (it does — used for in-place mapper swaps).
- Tests mock `mido` functions by monkeypatching `midi_router.midi_router.mido.*` to avoid
  hardware dependencies. Follow that pattern in new tests that exercise router lifecycle.
- Manager events: the manager exposes a listener API (`register_listener`) that the UI
  uses to receive start/stop/reload events. Listener callbacks should be tolerant and
  non-blocking (return quickly or be async coroutines that are awaited concurrently).

Integration points & external dependencies
- mido (MIDI library) + optional backends (python-rtmidi). Tests MUST mock mido calls.
- Textual (UI library): interactive app depends on Textual's lifecycle (async `on_mount`)
  and widget APIs. Unit tests avoid the full textual message pump by exercising `AsyncRouterManager`
  directly where possible.
- Control channel: a small TCP control server (127.0.0.1) exists for external reloads;
  tests bind to a free port and connect to it to issue `RELOAD\n` commands.

Code patterns & examples
- Debounced start (manager): callers call `await manager.start(config)` — manager coalesces
  multiple calls within a small interval and returns the router instance when started.
- Immediate UI updates: UI widgets should use manager events (register a coroutine listener)
  rather than polling for manager state.
- Config handling: the app uses `Config.from_yaml(stream=open('config.yaml'))` in `on_mount`.
  Tests may monkeypatch `Config.from_yaml` to return fixtures.

Testing tips for agents
- Mock mido functions in tests:
  ```py
  monkeypatch.setattr('midi_router.midi_router.mido.get_input_names', lambda: ['Input 1'])
  monkeypatch.setattr('midi_router.midi_router.mido.open_input', lambda name, callback=None: DummyPort(name))
  ```
- For control server tests, bind to a free port then call `manager.start_control_port(free_port)`.
- Avoid creating Textual apps in unit tests that rely on the message pump; instead test the
  manager and router lifecycle directly.

What agents should NOT do
- Avoid direct mutation of router.config in the UI thread; use manager APIs or router.update_config.
- Do not swallow general Exceptions. If there is a specific, expected error case, handle it explicitly. Otherwise, let exceptions propagate.
- Do not use getattr when attribute access is possible; it reduces code clarity.

If you edit these files, prioritize
1. `src/midi_router/midi_router.py` for router behavior and graceful shutdown semantics.
2. `src/midi_router/scripts/interactive.py` for UI/manager integration and tests that exercise
   lifecycle behavior.

Feedback
If anything here is unclear or missing, tell me which areas you want expanded (examples, more
commands, or more file references) and I'll iterate.

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

from rich.logging import RichHandler
from textual.app import App
from textual.containers import Center, Horizontal, Vertical, CenterMiddle
from textual.logging import TextualHandler
from textual.reactive import reactive
from textual.screen import ModalScreen, Screen
from textual.widget import Widget
from textual.widgets import Button, Header, Footer, Label, ListItem, ListView, RichLog
import yaml

from midi_router.config import Config, Mapping
from midi_router.midi_router import MidiRouter


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

    mappings: reactive[list[Mapping]] = reactive([], recompose=False)

    def __init__(self, mappings: list[Mapping]):
        super().__init__()
        self.mappings = mappings

    def compose(self):
        yield from (MappingListItem(mapping=mapping) for mapping in self.mappings)
        yield ListItem(Center(Button("Add Mapping")))

    async def action_popup_editor(self):
        logging.debug(f"Popup editor for mapping: {self.highlighted_child}")
        await self.run_action(f"app.set_active_mapping_index({self.index})")
        await self.run_action("app.push_screen('mapping-editor')")

class Routes(Widget):
    """Render the current configuration's routes."""
    midi_router: reactive[MidiRouter|None] = reactive(None, recompose=True)

    def compose(self):
        yield MappingListView(self.midi_router.config.mappings if self.midi_router else []).focus()

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
                yield rich_log
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


class MidiRouterApp(App):
    CSS_PATH = "midi-router-interactive.tcss"
    #SCREENS = {'mapping-editor': MappingEditor}

    midi_router: reactive[MidiRouter|None] = reactive(None, recompose=False)
    active_mapping_index: reactive[int] = reactive(0, recompose=False)

    def on_mount(self):
        config = Config.from_yaml(stream=open("config.yaml"))
        self.midi_router = MidiRouter(config)
        # TESTING
        # import asyncio
        # self.midi_router.async_run()
        #asyncio.create_task(self.midi_router.async_run())
        logging.debug(f"App Mounted with config: {yaml.dump(self.midi_router.config.model_dump())}")
        main_screen = MainScreen()
        main_screen.data_bind(MidiRouterApp.midi_router)
        editor_screen = MappingEditor()
        editor_screen.data_bind(MidiRouterApp.midi_router)
        editor_screen.data_bind(MidiRouterApp.active_mapping_index)
        self.install_screen(main_screen, name="main")
        self.install_screen(editor_screen, name="mapping-editor")
        self.push_screen("main")


    def action_set_active_mapping_index(self, index: int):
        self.active_mapping_index = index
        logging.debug(f"Set active mapping index: {self.active_mapping_index}")



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

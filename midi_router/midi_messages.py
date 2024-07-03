from typing import Annotated, Iterable, Union

import pydantic


Channel = Annotated[int, pydantic.Field(ge=0, le=15)]
FrameType = Annotated[int, pydantic.Field(ge=0, le=7)]
FrameValue = Annotated[int, pydantic.Field(ge=0, le=7)]
Control	= Annotated[int, pydantic.Field(ge=0, le=127)]
Note = Annotated[int, pydantic.Field(ge=0, le=127)]
Program	= Annotated[int, pydantic.Field(ge=0, le=127)]
Song = Annotated[int, pydantic.Field(ge=0, le=127)]
Value = Annotated[int, pydantic.Field(ge=0, le=127)]
Velocity = Annotated[int, pydantic.Field(ge=0, le=127)]
Data = Iterable[Annotated[int, pydantic.Field(ge=0, le=127)]]
Pitch = Annotated[int, pydantic.Field(ge=-8192, le=8191)]
Pos	= Annotated[int, pydantic.Field(ge=0, le=16383)]
Time = Union[int, float]


class _MidiMessage(pydantic.BaseModel):
    pass


class NoteOff(_MidiMessage):
    channel: Channel
    note: Note
    velocity: Velocity = 64

class NoteOn(_MidiMessage):
    channel: Channel
    note: Note
    velocity: Velocity = 64

class Polytouch(_MidiMessage):
    channel: Channel
    note: Note
    value: Value
    
class ControlChange(_MidiMessage):
    channel: Channel
    control: Control
    value: Value
    
class ProgramChange(_MidiMessage):
    channel: Channel
    program: Program

class AfterTouch(_MidiMessage):
    chanenel: Channel
    value: Value

class PitchWheel(_MidiMessage):
    channel: Channel
    pitch: Pitch

class SystemExclusive(_MidiMessage):
    data: Data

class QuarterFrame(_MidiMessage):
    frame_type: FrameType
    frame_value: FrameValue

class SongPos(_MidiMessage):
    pos: Pos

class SongSelect(_MidiMessage):
    song: Song
    
class TuneRequest(_MidiMessage):
    pass
    
class Clock(_MidiMessage):
    pass
    
class Start(_MidiMessage):
    pass
    
class Continue(_MidiMessage):
    pass
    
class Stop(_MidiMessage):
    pass
    
class Active_sensing(_MidiMessage):
    pass
    
class Reset(_MidiMessage):
    pass	

from abc import ABC
from collections import Counter
from enum import Enum
import itertools
import re
import string
from typing import Literal, Optional

import pydantic
import pydantic.types
import pydantic_core
import yaml


port_long_name_re = re.compile(r"(?P<name>.*) (?P<port>\d+:\d+)")

class PortType(Enum):
    USB = "USB"
    DIN = "DIN"

class PortConstant(Enum):
    ALL = "ALL"

class ChannelConstant(Enum):
    ALL = "ALL"
    

class Port(pydantic.BaseModel, ABC):
    identifier: pydantic.types.StrictStr
    name: pydantic.types.StrictStr
    port: Optional[pydantic.types.StrictStr] = pydantic.Field(default=None, pattern=r"\d+:\d+")
    port_type: PortType

    @pydantic.field_validator("port_type")
    @classmethod
    def validate_only_usb_supported(cls, v, info):
        if v != PortType.USB:
            raise NotImplementedError("Only USB port types are supported at this time.")
        return v

    @staticmethod
    def parse_long_port_name(long_name):
        re_match = port_long_name_re.match(long_name)
        if re_match:
            return re_match.group("name"), re_match.group("port")
        else:
            return long_name, None


    @property
    def long_name(self):
        if self.port:
            return f"{self.name} {self.port}"
        else:
            return self.name

    @long_name.setter
    def set_long_name(self, long_name):
        self.name, self.port = self.parse_long_port_name(long_name)


class InputPort(Port):
    pass
        

class OutputPort(Port):
    pass


class PortSpecifier(pydantic.BaseModel):
    identifier: pydantic.types.StrictStr

    def __hash__(self):
        return hash(self.identifier)


class Mapping(pydantic.BaseModel):
    from_port: PortSpecifier | PortConstant = PortConstant.ALL
    to_port: PortSpecifier | PortConstant = PortConstant.ALL
    from_channel: int | ChannelConstant = ChannelConstant.ALL
    to_channel: int | ChannelConstant = ChannelConstant.ALL
    

class PortsConfig(pydantic.BaseModel):
    inputs: list[InputPort]
    outputs: list[InputPort]
    

class Config(pydantic.BaseModel):
    ports: PortsConfig
    mappings: list[Mapping]

    @pydantic.model_validator(mode='after')
    def validate_identifiers(self):
        input_port_identifiers = [port.identifier for port in self.ports.inputs]
        input_port_identifiers_set = set(input_port_identifiers)
        output_port_identifiers = [port.identifier for port in self.ports.outputs]
        output_port_identifiers_set = set(output_port_identifiers)
        all_port_identifiers = input_port_identifiers + output_port_identifiers
        all_port_identifiers_set = input_port_identifiers_set | output_port_identifiers_set

        if len(all_port_identifiers_set) != len(all_port_identifiers):
            counts = Counter(all_port_identifiers)
            duplicate_identifiers = [identifier for identifier, count in counts.items() if count > 1]
            raise ValueError("Duplicate port identifiers are not allowed: " + ", ".join(duplicate_identifiers))

        bad_from_port_errors = [
            f"mappings.{mapping_index}.from_port.identifier\n    Unknown input port identifier: {mapping.from_port.identifier}"
            for mapping_index, mapping in enumerate(self.mappings)
            if isinstance(mapping.from_port, PortSpecifier) and mapping.from_port.identifier not in input_port_identifiers_set
        ]
        bad_to_port_errors = [
            f"mappings.{mapping_index}.to_port.identifier\n    Unknown output port identifier: {mapping.to_port.identifier}"
            for mapping_index, mapping in enumerate(self.mappings)
            if isinstance(mapping.to_port, PortSpecifier) and mapping.to_port.identifier not in output_port_identifiers_set
        ]

        if bad_from_port_errors or bad_to_port_errors:
            all_bad_port_errors = bad_from_port_errors + bad_to_port_errors
            raise pydantic_core.PydanticCustomError('invalid_specifier', "\n".join(all_bad_port_errors))
            
        return self
        
    
    def to_yaml(self, stream=None, sort_keys=False):
        return yaml.safe_dump(self.model_dump(mode="json"), stream=stream, sort_keys=sort_keys)

    @classmethod
    def from_yaml(cls, stream):
        return cls.model_validate(yaml.safe_load(stream))


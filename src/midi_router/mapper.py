import logging

from midi_router import config


logger = logging.getLogger("midi_router")


class Transform:
    def __init__(self, name, func):
        self.name = name
        self._func = func

    def __call__(self, message):
        return self._func(message)

    def __str__(self):
        return f"<{self.name}>"


class Mapper:
    def __init__(self, from_ports, to_ports, filter=None, transform=None, mapping_config=None):
        self.from_ports = from_ports
        self.to_ports = to_ports
        self.mapping_config = mapping_config
        self.filter = filter or (lambda message: True)
        self.transform = transform or Transform("noop", (lambda message: message))

    @classmethod
    def from_mapping_config(cls, mapping_config, input_ports_by_identifier, output_ports_by_identifier):
        from_ports = (
            list(input_ports_by_identifier.values())
            if mapping_config.from_port == config.PortConstant.ALL
            else [
                port
                for identifier in [mapping_config.from_port.identifier]
                if (port := input_ports_by_identifier.get(identifier)) is not None
            ]
        )
        to_ports = (
            list(output_ports_by_identifier.values())
            if mapping_config.to_port == config.PortConstant.ALL
            else [
                port
                for identifier in [mapping_config.to_port.identifier]
                if (port := output_ports_by_identifier.get(identifier)) is not None
            ]
        )

        filter = None
        if mapping_config.from_channel != config.ChannelConstant.ALL:
            def _filter(message):
                channel = getattr(message, "channel", None)
                return channel is None or channel == mapping_config.from_channel
            filter = _filter

        transform = None
        if mapping_config.to_channel != config.ChannelConstant.ALL and mapping_config.to_channel != mapping_config.from_channel:
            def _transform(message):
                return (
                    message.copy(channel=mapping_config.to_channel)
                    if hasattr(message, "channel")
                    else message
                )
            transform = Transform(f"channel {mapping_config.from_channel} => channel {mapping_config.to_channel}", _transform)

        mapping = cls(from_ports=from_ports, to_ports=to_ports, filter=filter, transform=transform,
                mapping_config=mapping_config)
        return mapping

    def send(self, from_port_name, message):
        if self.filter(message):
            #logger.info(f"from {from_port_name}: {message}")
            transformed = self.transform(message)
            for to_port in self.to_ports:
                if to_port.name != from_port_name:
                    if hasattr(message, "channel"):
                        logger.info(f"  to {to_port.name}: {transformed}")
                    to_port.send(transformed)
            #logger.info("\n")


    def dict(self):
        #if self.mapping_config is not None:
        #    return self.mapping_config.dict()
        return {
            "from_ports": [
                from_port.name
                for from_port in self.from_ports
            ],
            "to_ports": [
                to_port.name
                for to_port in self.to_ports
            ],
            "transform": str(self.transform),
        }

    def __repr__(self):
        return f"{self.__class__.__name__}(from_ports={self.from_ports}, to_ports={self.to_ports})"

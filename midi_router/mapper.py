import logging

from midi_router import config


logger = logging.getLogger("midi_router")


class Mapper:
    def __init__(self, from_ports, to_ports, filter=None, transform=None, mapping_config=None):
        self.from_ports = from_ports
        self.to_ports = to_ports
        self.mapping_config = mapping_config
        self.filter = filter or (lambda message: True)
        self.transform = transform or (lambda message: message)

    @classmethod
    def from_mapping_config(cls, mapping_config, identifiers_to_input_port_infos, input_ports_by_long_name,
                            identifiers_to_output_port_infos, output_ports_by_long_name):
        from_ports = (
            input_ports_by_long_name.values()
            if mapping_config.from_port == config.PortConstant.ALL
            else [
                port
                for long_name in [
                    identifiers_to_input_port_infos[mapping_config.from_port.identifier].long_name
                ]
                if (port := input_ports_by_long_name.get(long_name)) is not None
            ]
        )
        to_ports = (
            output_ports_by_long_name.values()
            if mapping_config.to_port == config.PortConstant.ALL
            else [
                port
                for long_name in [
                    identifiers_to_output_port_infos[mapping_config.to_port.identifier].long_name
                ]
                if (port := output_ports_by_long_name.get(long_name)) is not None
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
            transform = _transform

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
        if self.mapping_config is not None:
            return self.mapping_config.dict()
        return {
            "from_ports": [
                from_port.name
                for from_port in self.from_ports
            ],
            "to_ports": [
                to_port.name
                for to_port in self.to_ports
            ],
        }

    def __repr__(self):
        return f"{self.__class__.__name__}(from_ports={self.from_ports}, to_ports={self.to_ports})"

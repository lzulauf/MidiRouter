import random
import string

import mido
import wonderwords

from midi_router import config

def generate_port_identifier(starting_letter=None):
    if starting_letter is None:
        starting_letter = random.choice(string.ascii_lowercase)
    word_generator = wonderwords.RandomWord()

    params = {
        "starts_with": starting_letter,
        "regex": r"[a-z]+",
        "word_min_length": 3,
        "word_max_length": 7,
    }
        
    noun = word_generator.word(**params, include_categories=["noun"])
    adjective = word_generator.word(**params, include_categories=["adjective"])    
    
    return f"{adjective}_{noun}"
    
def port_identifiers_generator():
    index = 0
    while True:
        yield generate_port_identifier(starting_letter=string.ascii_lowercase[index % len(string.ascii_lowercase)])
        index += 1


def generate_default_config():
    port_generator = port_identifiers_generator()
    return config.Config(
        ports=config.PortsConfig(
            inputs=[
                config.InputPort(
                    identifier=f"in_{next(port_generator)}",
                    name=config.Port.parse_long_port_name(long_name)[0],
                    port=config.Port.parse_long_port_name(long_name)[1],
                    port_type=config.PortType.USB,
                )
                for long_name in mido.get_input_names()
            ],
            outputs=[
                config.InputPort(
                    identifier=f"out_{next(port_generator)}",
                    name=config.Port.parse_long_port_name(long_name)[0],
                    port=config.Port.parse_long_port_name(long_name)[1],
                    port_type=config.PortType.USB,
                )
                for long_name in mido.get_output_names()
            ],
        ),
        mappings=[
            config.Mapping()
        ],
    )




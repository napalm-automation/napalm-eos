from napalm_eos.eos import EOSDriver

import napalm_yang

import pprint


eos_configuration = {
    'hostname': '127.0.0.1',
    'username': 'vagrant',
    'password': 'vagrant',
    'optional_args': {'port': 12443}
}


d = EOSDriver(**eos_configuration)
d.open()

# Get current interfaces configuration
running = d.parse_config("interfaces")

# Print the exact model as defined by OC
# This is mostly informative, as quick reference
print(running.model_to_text())

# We can get a representation of the data in text
print(running.data_to_text())

# Or as a dict
pprint.pprint(running.data_to_dict())

# We can also translate the object backto native configuration
print(d.translate_model(running, "interfaces"))

# Let's change some configuration
candidate = d.parse_config("interfaces")
candidate.interfaces.interface["Management1"].config.description("Connected to oob1:et2")
candidate.interfaces.interface["Ethernet2"].config.description("Connected to spine")
candidate.interfaces.interface["Port-Channel1"].config.description("Connected to blah")
candidate.interfaces.interface["Loopback1"].config.enabled(False)

# Let's create a new loopback interface
candidate.interfaces.interface.new_element("Loopback0")
candidate.interfaces.interface["Loopback0"].name("Loopback0")
candidate.interfaces.interface["Loopback0"].config.name("Loopback0")
candidate.interfaces.interface["Loopback0"].config.description("loopback0")
candidate.interfaces.interface["Loopback0"].config.enabled(True)
candidate.interfaces.interface["Loopback0"].config.mtu(1500)
candidate.interfaces.interface["Loopback0"].hold_time.config.up(0)
candidate.interfaces.interface["Loopback0"].hold_time.config.down(0)
candidate.interfaces.interface["Loopback0"].config.type_(napalm_yang.ianaift.Softwareloopback)

# Let's see a diff of the running and the candidate configuration
pprint.pprint(running.diff(candidate))

# Let's turn this into native configuration
new_config = d.translate_model(candidate, "interfaces")
print(new_config)


# Load it into the device
d.load_merge_candidate(config=new_config)

# See the diff matches our expectations
print(d.compare_config())

# Let's commit the configuration now
d.commit_config()

# if now get a new running and candidate config, let's compare it with out previous candidate
running = d.parse_config("interfaces")
pprint.pprint(running.diff(candidate))

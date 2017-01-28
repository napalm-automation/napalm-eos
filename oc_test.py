from napalm_eos.eos import EOSDriver


def print_data(name, data, indentation=""):
    meta = data["_meta"]
    mode = "rw" if meta["config"] else "ro"
    key = "* [{}]".format(meta.get("key", "")) if meta.get("key", "") else ""
    print("{}+-- {} {}{}".format(indentation, mode, name, key))
    indentation = indentation + "|  "

    for attr, attr_data in data.items():
        if attr == "_meta":
            continue
        elif attr == "list":
            for e, d in attr_data.items():
                print_data(e, d, indentation)
        elif "value" in attr_data.keys():
            sm = attr_data["_meta"]

            if sm["type"] == "Enumeration":
                try:
                    value = "{} ({})".format(attr_data["value"], attr_data["enum_value"])
                except:
                    raise Exception(attr_data)
            else:
                value = attr_data["value"]

            mandatory = "" if sm["mandatory"] else "?"
            body = "{}+-- {} {}{}".format(indentation, mode, attr, mandatory)
            spacing = " " * (60 - len(body))
            print("{}{}{}".format(body, spacing, value))
        else:
            print_data(attr, attr_data, indentation)


eos_configuration = {
    'hostname': '127.0.0.1',
    'username': 'vagrant',
    'password': 'vagrant',
    'optional_args': {'port': 12443}
}


d = EOSDriver(**eos_configuration)
d.open()
d.oc_populate_interfaces()
print_data("interfaces", d.interfaces.data_representation())
print("==========")
print(d.translate_yang_model(d.interfaces))

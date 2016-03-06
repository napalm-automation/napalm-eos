"""Methods to manage configuration on an EOS node."""

from datetime import datetime
from napalm_base.exceptions import SessionLockedException, ReplaceConfigException, MergeConfigException
import pyeapi


def _lock_session(node):
    if node.config_session is not None:
        raise SessionLockedException('Session is already in use by napalm')
    else:
        node.config_session = 'napalm_{}'.format(datetime.now().microsecond)


def _create_config_session(node, filename, config, replace):
    commands = list()
    commands.append('configure session {}'.format(node.config_session))

    if replace:
        commands.append('rollback clean-config')

    if filename is not None:
        with open(filename, 'r') as f:
            lines = f.readlines()
    else:
        if isinstance(config, list):
            lines = config
        else:
            lines = config.splitlines()

    for line in lines:
        line = line.strip()
        if line == '':
            continue
        if line.startswith('!'):
            continue
        commands.append(line)

    return commands


def load_config(node, filename=None, config=None, replace=True):
    """
    Load configuration on a node.

    :param node: (EOSDriver) A node to operate on.
    :param filename: (str) A filename to load the configuration from.
    :param config: (str) A string representation of the configuration. Used if filename is None.
    :param replace: (boolean) Wether to merge or replace the configuration.

    """
    _lock_session(node)
    commands = _create_config_session(node, filename, config, replace)

    try:
        node.device.run_commands(commands)
    except pyeapi.eapilib.CommandError as e:
        node.discard_config()

        if replace:
            raise ReplaceConfigException(e.message)
        else:
            raise MergeConfigException(e.message)


def compare_config(node):
    """Implemantation of NAPALM method compare_config."""
    if node.config_session is None:
        return ''
    else:
        commands = ['show session-config named %s diffs' % node.config_session]
        result = node.device.run_commands(commands, encoding='text')[0]['output']

        result = '\n'.join(result.splitlines()[2:])

        return result.strip()


def commit_config(node):
    """Implemantation of NAPALM method commit_config."""
    commands = list()
    commands.append('copy startup-config flash:rollback-0')
    commands.append('configure session {}'.format(node.config_session))
    commands.append('commit')
    commands.append('write memory')

    node.device.run_commands(commands)
    node.config_session = None


def discard_config(node):
    """Implemantation of NAPALM method discard_config."""
    if node.config_session is not None:
        commands = list()
        commands.append('configure session {}'.format(node.config_session))
        commands.append('abort')
        node.device.run_commands(commands)
        node.config_session = None


def rollback(node):
    """Implemantation of NAPALM method rollback."""
    commands = list()
    commands.append('configure replace flash:rollback-0')
    commands.append('write memory')
    node.device.run_commands(commands)

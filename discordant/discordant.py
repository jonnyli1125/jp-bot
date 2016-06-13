import json
import re
import sys
from collections import namedtuple
from inspect import iscoroutinefunction
from os import path

import discord
import requests

from discordant.utils import is_url

Command = namedtuple('Command', ['name', 'arg_func', 'aliases'])


class Discordant(discord.Client):
    _CMD_NAME_REGEX = re.compile(r'[a-z0-9]+')
    _handlers = {}
    _commands = {}
    _aliases = {}
    _triggers = set()

    def __init__(self, config_file='config.json'):
        super().__init__()

        self.__email = ''  # prevent a conflict with discord.Client#email
        self._password = ''
        self._token = ''
        self.command_char = ''
        self.controllers = []
        self.config = {}

        self.load_config(config_file)

    def run(self):
        if self._token:
            super().run(self._token)
        else:
            super().run(self.__email, self._password)

    def load_config(self, config_file):
        if is_url(config_file):
            self.config = requests.get(config_file).json()
        elif not path.exists(config_file):
            print("No config file found (expected '{}').".format(config_file))
            print("Copy config-example.json to", config_file,
                  "and edit it to use the appropriate settings.")
            sys.exit(-1)
        else:
            with open(config_file, "r") as f:
                self.config = json.load(f)
        if 'token' in self.config['login']:
            self._token = self.config['login']['token']
        else:
            self.__email = self.config['login']['email']
            self._password = self.config['login']['password']
        self.command_char = self.config['commands']['command_char']
        self.controllers = self.config["client"]["controllers"]
        self.load_aliases()

    def load_aliases(self):
        aliases = self.config['aliases']
        for base_cmd, alias_list in aliases.items():
            cmd_name = self._aliases[base_cmd]

            for alias in alias_list:
                self._aliases[alias] = cmd_name
                self._commands[cmd_name].aliases.append(alias)

    async def on_ready(self):
        await self.change_status(
            game=discord.Game(name=self.config["client"]["game"])
            if self.config["client"]["game"] else None)

    async def on_message(self, message):
        # TODO: logging
        if message.content.startswith(self.command_char) and \
                        message.author != self.user:
            await self.run_command(message)
            return

        for handler_name, trigger in self._handlers.items():
            match = trigger.search(message.content)
            if match is not None:
                await getattr(self, handler_name)(match, message)
            # do we return after the first match? or allow multiple matches

    async def run_command(self, message):
        cmd_name, *args = message.content.split(' ')
        cmd_name = cmd_name[1:]
        args = ' '.join(args).strip()

        if cmd_name in self._aliases:
            cmd = self._commands[self._aliases[cmd_name]]
            args = cmd.arg_func(args)
            await getattr(self, cmd.name)(args, message)

    @classmethod
    def register_handler(cls, trigger, regex_flags=0):
        try:
            trigger = re.compile(trigger, regex_flags)
        except re.error as err:
            print('Invalid trigger "{}": {}'.format(trigger, err.msg))
            sys.exit(-1)

        if trigger.pattern in cls._triggers:
            print('Cannot reuse pattern "{}"'.format(trigger.pattern))
            sys.exit(-1)

        cls._triggers.add(trigger.pattern)

        def wrapper(func):
            if not iscoroutinefunction(func):
                print('Handler for trigger "{}" must be a coroutine'.format(
                    trigger.pattern))
                sys.exit(-1)

            func_name = '_trg_' + func.__name__
            # disambiguate the name if another handler has the same name
            while func_name in cls._handlers:
                func_name += '_'

            setattr(cls, func_name, func)
            cls._handlers[func_name] = trigger

        return wrapper

    @classmethod
    def register_command(cls, name, aliases=None, arg_func=lambda args: args):
        if aliases is None:
            aliases = []
        aliases.append(name)

        def wrapper(func):
            if not iscoroutinefunction(func):
                print('Handler for command "{}" must be a coroutine'.format(
                    name))
                sys.exit(-1)

            func_name = '_cmd_' + func.__name__
            while func_name in cls._commands:
                func_name += '_'

            setattr(cls, func_name, func)
            cls._commands[func_name] = Command(func_name, arg_func, aliases)
            # associate the given aliases with the command
            for alias in aliases:
                if alias in cls._aliases:
                    print('The alias "{}"'.format(alias),
                          'is already in use for command',
                          cls._aliases[alias][:5].strip('_'))
                    sys.exit(-1)
                if cls._CMD_NAME_REGEX.match(alias) is None:
                    print('The alias "{}"'.format(alias),
                          ('is invalid. Aliases must only contain lowercase'
                           ' letters or numbers.'))
                    sys.exit(-1)
                cls._aliases[alias] = func_name

        return wrapper

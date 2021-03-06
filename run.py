#!/usr/bin/env python3
from discordant import Discordant, configure_logging


if __name__ == '__main__':
    configure_logging()

    bot = Discordant()
    try:
        bot.run()
    except KeyboardInterrupt:
        print('Exiting...')

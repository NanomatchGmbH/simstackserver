#!/usr/bin/env python

import sys, os

from SimStackServer.SimStackServer import SimStackServer, AlreadyRunningException


def get_my_runtime():
    me = os.path.abspath(os.path.realpath(__file__))
    return me

if __name__ == '__main__':
    my_runtime = get_my_runtime()
    try:
        # We try to silently start a new server
        ss = SimStackServer(my_runtime)
        ss.main_loop()
    except AlreadyRunningException as e:
        # In case we are already running we silently discard and exit.
        pass
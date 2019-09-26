#!/usr/bin/env python

import sys, os


from os.path import join

if __name__ == '__main__':
    base_path = os.path.dirname(os.path.realpath(__file__))
    dir_path = join(base_path,"external","clusterjob")
    if not dir_path in sys.path:
        sys.path.append(dir_path)

    dir_path = join(base_path,"external","python-crontab")
    if not dir_path in sys.path:
        sys.path.append(dir_path)

from SimStackServer.SimStackServer import SimStackServer, AlreadyRunningException

def get_my_runtime():
    me = os.path.abspath(os.path.realpath(__file__))
    return me

if __name__ == '__main__':
    my_runtime = get_my_runtime()
    try:
        # We try to silently start a new server
        ss = SimStackServer(my_runtime)
        if len(sys.argv) >= 2:
            wf_filename = sys.argv[1]
            ss.main_loop(wf_filename)
        else:
            ss.main_loop()
    except AlreadyRunningException as e:
        # In case we are already running we silently discard and exit.
        pass

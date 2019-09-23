#!/usr/bin/env python

import sys, os
import time

from SimStackServer import ClusterManager
from SimStackServer.Config import Config

def get_my_runtime():
    me = os.path.abspath(os.path.realpath(__file__))
    return me

if __name__ == '__main__':
    config = Config()
    if config.is_running():
        sys.exit(0)

    config.register_pid()
    #Workblock start
    try:
        me = get_my_runtime()
        #We register with crontab:
        config.register_crontab(me)
        work_done = False


        ###
        if work_done:
            config.unregister_crontab()
        #cm = ClusterManager()
        #cm.run()
    except Exception as e:
        config.teardown_pid()
        raise e
    #Workblock end


    config.teardown_pid()

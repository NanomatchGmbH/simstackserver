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

        ### Testing logfile:
        mycounter = 0
        maxcount = 23
        test_logfile = "/home/strunk/outlogfile.txt"
        if os.path.exists(test_logfile):
            with open(test_logfile, 'rt') as outfile:
                mycounter = int(outfile.read())

        for i in range(0,maxcount):
            time.sleep(2)
            mycounter += 1
            with open(test_logfile, 'wt') as outfile:
                outfile.write("%d" % mycounter)
            if mycounter >= maxcount:
                break



        ###
        if mycounter >= maxcount:
            config.unregister_crontab()
        #cm = ClusterManager()
        #cm.run()
    except Exception as e:
        config.teardown_pid()
        raise e
    #Workblock end


    config.teardown_pid()

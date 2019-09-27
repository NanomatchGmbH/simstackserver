#!/usr/bin/env python

import sys, os
import time
import lockfile
import zmq


from os.path import join

from zmq.auth.thread import ThreadAuthenticator

if __name__ == '__main__':
    base_path = os.path.dirname(os.path.realpath(__file__))
    dir_path = join(base_path,"external","clusterjob")
    if not dir_path in sys.path:
        sys.path.append(dir_path)

    dir_path = join(base_path,"external","python-crontab")
    if not dir_path in sys.path:
        sys.path.append(dir_path)

    dir_path = join(base_path,"external","python-daemon")
    if not dir_path in sys.path:
        sys.path.append(dir_path)

from SimStackServer.SimStackServer import SimStackServer, AlreadyRunningException
from SimStackServer.Config import Config
import daemon

def get_my_runtime():
    #me = os.path.abspath(os.path.realpath(__file__))
    me = sys.executable + " " + sys.argv[0]
    return me

def random_pass():
    random_bytes=os.urandom(48)
    import base64
    return base64.b64encode(random_bytes).decode("utf8")[:-2]

def setup_pid():
    from SimStackServer.Util.NoEnterPIDLockFile import NoEnterPIDLockFile
    return NoEnterPIDLockFile(Config._get_config_file("SimStackServer_setup.pid"), timeout = 0.0)

if __name__ == '__main__':
    # We register another pid just for setup, because it takes three seconds from here to the Tag "PIDFILE TAKEOVER"
    setup_pidfile = setup_pid()
    try:
        setup_pidfile.acquire(timeout = 0.0)
    except lockfile.AlreadyLocked as e:
        sys.exit(0)

    my_runtime = get_my_runtime()
    try:
        # We try to silently start a new server
        ss = SimStackServer(my_runtime)
        try:
            mypidfile = ss.register_pidfile()
            mypidfile.acquire(timeout = 0.0)
        except lockfile.AlreadyLocked as e:
            raise AlreadyRunningException("Second stage locking did not work.") from e
    except AlreadyRunningException as e:
        #print("Exiting, because lock exists.")
        #print("PID was",SimStackServer.register_pidfile().read_pid())
        # In case we are already running we silently discard and exit.
        setup_pidfile.release()
        sys.exit(0)
    try:
        # We should be locked and running here:
        # Start a zero mq context
        context = zmq.Context()
        auth = ThreadAuthenticator(context)
        auth.start()
        auth.allow('127.0.0.1')
        mysecret = random_pass()
        auth.configure_plain(domain = '*', passwords = {"simstack_client":mysecret})
        socket = context.socket(zmq.REP)
        socket.plain_server = True
        myport = socket.bind_to_random_port('tcp://127.0.0.1', max_tries=400)

        appdirs = ss.get_appdirs()
        with open(join(appdirs.user_config_dir,"portconfig.txt"),'wt') as outfile:
            towrite = "Port, Secret %d %s\n"%(myport,mysecret)
            outfile.write(towrite)
            print(towrite[:-1])

        sys.stdout.flush()
        workdir = appdirs.user_cache_dir
        mystd = join(appdirs.user_log_dir, "sss.stdout")
        mystderr = join(appdirs.user_log_dir, "sss.stderr")
        mystdfileobj = open(mystd,'at')
        mystderrfileobj = open(mystderr,'at')
    except Exception as e:
        setup_pidfile.release()
        raise e
    try:
        # Careful: We close all files here
        with daemon.DaemonContext(
            stdout = mystdfileobj,
            stderr = mystderrfileobj,
            pidfile = mypidfile
        ):
            mypidfile.update_pid_to_current_process() # "PIDFILE TAKEOVER

            # At this point the daemon pid is in the correct pidfile and we can remove the setup pid with break_open
            # Reason we have to break it is because we are in another process.
            setup_pidfile.break_lock()

            a = socket.recv()
            print("Got something %s"%a)
            socket.send(b"World")

            time.sleep(5)

            if len(sys.argv) >= 2:
                wf_filename = sys.argv[1]
                ss.main_loop(wf_filename)
            else:
                ss.main_loop()
    except lockfile.AlreadyLocked:
        # This here happens, if in between the opening of the stdout and stderr another task took over and locked the file
        # It's rare, but I was able to reproduce it.
        pass




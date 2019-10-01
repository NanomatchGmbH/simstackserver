#!/usr/bin/env python

import sys, os
import time
import lockfile
import zmq
import socket


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

class InputFileError(Exception):
    pass

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

def get_open_port():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("",0))
    s.listen(1)
    port = s.getsockname()[1]
    s.close()
    return port

def flush_port_and_password_to_stdout(appdirs, other_process_setup = False):
    myfile = join(appdirs.user_config_dir,"portconfig.txt")
    if other_process_setup and not os.path.exists(myfile):
        # In this case another process might just be in the process of writing this file.
        # We have to wait 5 seconds for it to appear
        time.sleep(5.0)
    with open(myfile, 'rt') as infile:
        line = infile.read()
        splitline = line.split()
        if not len(splitline) == 4:
            raise InputFileError("Input of portconfig was expected to be four fields, got <%s>"%line)
        port = int(splitline[2])
        mypass = splitline[3].strip()
        print("Port Pass %d %s"%(port, mypass))
        return
    raise InputFileError("Inputfile %s did not contain lines."%myfile)
       
    

if __name__ == '__main__':
    ### Startup works like this:
    # We check if another server is doing setup at the moment.
    # If that is the case, we try to read the current password and port and write it to stdout
    # Otherwise we lock the setup pid
    #
    # We try to make a new server. In this, we register another PID file
    # If the server is already running, we release the setup pid file and print the current password and port to stdout and quit
    # Otherwise we also acquire the server lock
    # We get a new port and guess a new password.
    #    Now we have to be fast, because we release the port and it could be reallocated in extreme cases.



    # We register another pid just for setup, because it takes three seconds from here to the Tag "PIDFILE TAKEOVER"
    appdirs = SimStackServer.get_appdirs()
    setup_pidfile = setup_pid()
    try:
        setup_pidfile.acquire(timeout = 0.0)
    except lockfile.AlreadyLocked as e:
        flush_port_and_password_to_stdout(appdirs, True)
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
        # print("Exiting, because lock exists.")
        # print("PID was",SimStackServer.register_pidfile().read_pid())
        # In case we are already running we silently discard and exit.
        flush_port_and_password_to_stdout(appdirs,False)
        setup_pidfile.release()
        sys.exit(0)
    try:
        # We should be locked and running here:
        # Start a zero mq context
        mysecret = random_pass()
        myport = get_open_port()

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
            #files_preserve = [socket_fd],
            pidfile = mypidfile
        ):
            mypidfile.update_pid_to_current_process() # "PIDFILE TAKEOVER
            ss.setup_zmq_port(myport, mysecret)
            # At this point the daemon pid is in the correct pidfile and we can remove the setup pid with break_open
            # Reason we have to break it is because we are in another process.
            setup_pidfile.break_lock()

            if len(sys.argv) >= 2:
                wf_filename = sys.argv[1]
                ss.main_loop(wf_filename)
            else:
                ss.main_loop()

            ss.terminate()

    except lockfile.AlreadyLocked:
        # This here happens, if in between the opening of the stdout and stderr another task took over and locked the file
        # It's rare, but I was able to reproduce it.
        pass




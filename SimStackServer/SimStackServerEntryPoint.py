#!/usr/bin/env python
import signal
import sys
import os
import time
import lockfile
import logging
import zmq
import contextlib


from os.path import join

from SimStackServer.SecureWaNos import SecureModeGlobal, SecureWaNos
from SimStackServer.Util.SocketUtils import get_open_port, random_pass

from SimStackServer.SimStackServerMain import SimStackServer, AlreadyRunningException
from SimStackServer.Config import Config
import daemon


class InputFileError(Exception):
    pass


def get_my_runtime():
    # me = os.path.abspath(os.path.realpath(__file__))
    me = sys.executable + " " + sys.argv[0]
    return me


def setup_pid():
    from SimStackServer.Util.NoEnterPIDLockFile import NoEnterPIDLockFile

    return NoEnterPIDLockFile(
        Config._get_config_file("SimStackServer_setup.pid"), timeout=0.0
    )


def flush_port_and_password_to_stdout(appdirs, other_process_setup=False):
    myfile = join(appdirs.user_config_dir, "portconfig.txt")
    if other_process_setup and not os.path.exists(myfile):
        # In this case another process might just be in the process of writing this file.
        # We have to wait 5 seconds for it to appear
        time.sleep(5.0)
    with open(myfile, "rt") as infile:
        line = infile.read()
        splitline = line.split()
        if not len(splitline) == 5:
            raise InputFileError(
                "Input of portconfig was expected to be four fields, got <%s>" % line
            )
        port = int(splitline[2])
        mypass = splitline[3].strip()
        print("Port Pass %d %s %s" % (port, mypass, zmq.zmq_version()))


def main():
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
        setup_pidfile.acquire(timeout=0.0)
    except lockfile.AlreadyLocked:
        try:
            flush_port_and_password_to_stdout(appdirs, True)
        except FileNotFoundError as e:
            if "portconfig.txt" in str(e):
                print(
                    "App Lock was found, but no portconfig. Most probably SimStackServer start process was interupted."
                )
                print(f"Please check logs and remove {setup_pidfile}")
                sys.exit(1)
            raise
    logfilehandler = Config._setup_root_logger()
    my_runtime = get_my_runtime()
    try:
        # We try to silently start a new server
        ss = SimStackServer(my_runtime)
        try:
            mypidfile = ss.register_pidfile()
            mypidfile.acquire(timeout=0.0)
        except lockfile.AlreadyLocked as e:
            raise AlreadyRunningException("Second stage locking did not work.") from e
    except AlreadyRunningException:
        # print("Exiting, because lock exists.")
        # print("PID was",SimStackServer.register_pidfile().read_pid())
        # In case we are already running we silently discard and exit.
        flush_port_and_password_to_stdout(appdirs, False)
        setup_pidfile.release()
        sys.exit(0)
    try:
        # We should be locked and running here:
        # Start a zero mq context
        mysecret = random_pass()
        myport = get_open_port()

        with open(join(appdirs.user_config_dir, "portconfig.txt"), "wt") as outfile:
            from SimStackServer import __version__ as server_version

            allversions = f"SERVER,{server_version},ZMQ,{zmq.zmq_version()}"
            towrite = f"Port, Secret {myport} {mysecret} {allversions}\n"
            outfile.write(towrite)
            print(towrite[:-1])
        sys.stdout.flush()

        mystd = join(appdirs.user_log_dir, "sss.stdout")
        mystderr = join(appdirs.user_log_dir, "sss.stderr")
        mystdfileobj = open(mystd, "at")
        mystderrfileobj = open(mystderr, "at")
    except Exception as e:
        setup_pidfile.release()
        raise e
    try:
        # Careful: We close all files here
        signal_map = {
            signal.SIGTERM: ss._signal_handler,
            signal.SIGINT: ss._signal_handler,
        }
        if "-D" in sys.argv:
            cm = contextlib.nullcontext()
        else:
            cm = daemon.DaemonContext(
                stdout=mystdfileobj,
                stderr=mystderrfileobj,
                files_preserve=[logfilehandler.stream],
                pidfile=mypidfile,
                signal_map=signal_map,
            )
        with cm:
            logger = logging.getLogger("Startup")
            # Set secure mode global asap
            if "--secure_mode" in sys.argv:
                SecureModeGlobal.set_secure_mode()
                SecureWaNos.get_instance()
            if SecureModeGlobal.get_secure_mode():
                logger.info("SimStackServer Secure Daemon Startup")
            else:
                logger.info("SimStackServer Daemon Startup")
            mypidfile.update_pid_to_current_process()  # "PIDFILE TAKEOVER
            logger.debug("PID written")
            ss.setup_zmq_port(myport, mysecret)
            logger.debug("ZMQ port setup finished")
            # At this point the daemon pid is in the correct pidfile and we can remove the setup pid with break_open
            # Reason we have to break it is because we are in another process.
            setup_pidfile.break_lock()
            logger.debug("Releasing setup PID")

            try:
                import aiida

                aiida.load_profile()
            except Exception:
                pass
            try:
                if (
                    len(sys.argv) >= 2
                    and "-D" not in sys.argv
                    and "--secure_mode" not in sys.argv
                ):
                    wf_filename = sys.argv[1]
                    ss.main_loop(wf_filename)
                else:
                    ss.main_loop()
            except Exception:
                logger.exception("Exception in main loop. Terminating.")

            ss.terminate()
            logger.debug("Releasing final PID")

    except lockfile.AlreadyLocked:
        # This here happens, if in between the opening of the stdout and stderr another task took over and locked the file
        # It's rare, but I was able to reproduce it.
        pass

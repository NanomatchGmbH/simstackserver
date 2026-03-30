#!/usr/bin/env python
import signal
import sys
import time
import lockfile
import logging
import contextlib


from os.path import join

from SimStackServer.SecureWaNos import SecureModeGlobal, SecureWaNos
from SimStackServer.Util.SocketUtils import get_open_port, random_pass

from SimStackServer.SimStackServerMain import SimStackServer, AlreadyRunningException
from SimStackServer.Config import Config, ServerConfig
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


def flush_port_and_password_to_stdout(other_process_setup=False):
    server_config = Config.load_server_config()
    if server_config is None and other_process_setup:
        # In this case another process might just be in the process of writing this file.
        # We have to wait 5 seconds for it to appear
        time.sleep(5.0)
        server_config = Config.load_server_config()
    if server_config is None:
        raise FileNotFoundError("No server_config.yml found")
    print(
        "Port Pass %d %s %s"
        % (
            server_config.rest_port,
            server_config.client_secret,
            server_config.server_version,
        )
    )


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
            flush_port_and_password_to_stdout(other_process_setup=True)
        except FileNotFoundError:
            print(
                "App Lock was found, but no server config. Most probably SimStackServer start process was interrupted."
            )
            print(f"Please check logs and remove {setup_pidfile}")
            sys.exit(1)
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
        # In case we are already running we silently discard and exit.
        flush_port_and_password_to_stdout()
        setup_pidfile.release()
        sys.exit(0)
    try:
        # We should be locked and running here:
        server_config = Config.load_server_config()
        if server_config is None:
            from SimStackServer import __version__ as server_version

            mysecret = random_pass()
            myport = get_open_port()
            allversions = f"SERVER,{server_version},REST,1.0"
            server_config = ServerConfig(
                rest_port=myport,
                client_secret=mysecret,
                server_version=allversions,
            )
        Config.apply_env_overrides(server_config)
        myport = server_config.rest_port
        mysecret = server_config.client_secret
        Config.save_server_config(server_config)
        flush_port_and_password_to_stdout()
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

            # Start FastAPI server
            # Default to loopback; set SIMSTACK_BIND_HOST=0.0.0.0 when running in Docker
            import os

            bind_host = os.environ.get("SIMSTACK_BIND_HOST", "127.0.0.1")
            fastapi_port = ss._start_fastapi_server(
                host=bind_host,
                port=myport,
                username="simstack",
                password=mysecret,
            )
            logger.info(f"FastAPI server started on port {fastapi_port}")

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

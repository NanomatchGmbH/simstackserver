import daemon.pidfile


class NoEnterPIDLockFile(daemon.pidfile.PIDLockFile):
    """
    This class is a carbon copy of PIDLockFile with the one difference that it does not lock on enter.
    Using this class, we can create a lock and pass it to python-daemon without it locking again.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def __enter__(self):
        return self

    def update_pid_to_current_process(self):
        # Basically we are moving the lock from process to process.
        # Bad code
        # Better would be to overwrite the lock.
        self.break_lock()
        self.acquire()

class InternalBatchSystem:
    _processfarm = None
    _processfarm_thread = None

    def __init__(self):
        pass

    @classmethod
    def get_instance(cls):
        from threadfarm.processfarm import ProcessFarm

        if cls._processfarm is None:
            assert cls._processfarm_thread is None
            (
                cls._processfarm_thread,
                cls._processfarm,
            ) = ProcessFarm.start_processfarm_as_thread()
        return cls._processfarm, cls._processfarm_thread

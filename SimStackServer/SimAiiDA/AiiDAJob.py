from aiida.manage import manager
from aiida.manage.database.delete.nodes import delete_nodes
from aiida.orm import load_node


class AiiDAJob:
    def __init__(self, jobuuid):
        self._my_uuid = jobuuid
        self._mynode = load_node(self._my_uuid)
        print("Found node", self._mynode)
        if self._mynode.is_excepted:
            print(self._mynode.exception)

    def kill(self):
        controller = manager.get_manager().get_process_controller()
        controller.kill_process(self._mynode.pk)

    def status(self):
        if self._mynode.is_finished_ok:
            return "completed"
        elif self._mynode.is_excepted or self._mynode.is_killed:
            return "crashed"
        elif self._mynode.is_sealed:
            return "inprogress"
        else:
            return "crashed"

    def delete(self):
        delete_nodes([self._mynode.pk], force=True)

    def listdir(self):
        wdir = self._mynode.get_remote_workdir()
        print(wdir)
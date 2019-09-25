import json
import time

from lxml import etree

import logging

#from SimStackServer import ClusterManager
from SimStackServer.Config import Config
from SimStackServer.WorkflowModel import Workflow


class AlreadyRunningException(Exception):
    pass


"""Tomorrow

Add indirection to workflow model (graph running -> module)
list of running wanos has to go into workflow model
check status somehow
file copy from to

"""

class WorkflowManager(object):
    def __init__(self):
        self._inprogress = []
        self._finished = []
        self._inprogress_models = []
        self._finished_models = []

    def from_json(self, filename):
        with open(filename, 'rt') as infile:
            mydict = json.load(infile)
        self._inprogress = mydict["inprogress"]
        self._finished = mydict["finished"]

    @staticmethod
    def _parse_xml(filename):
        with open(filename,'rt') as infile:
            xml = etree.parse(infile).getroot()
        return xml

    def _recreate_models(self):
        for source,target_models in zip([self._inprogress,self._finished],[self._inprogress_models,self._finished_models]):
            for mydict in source:
                filename = mydict["filename"]
                xml = self._parse_xml(filename)
                wf = Workflow()
                wf.from_xml(xml)
                target_models.append(wf)

    def to_json(self, filename):
        mydict = {
            "inprogress":self._inprogress,
            "finished": self._finished
        }
        with open(filename, 'wt') as outfile:
            json.dump(mydict, outfile)

    def check_status_submit(self):
        for wfmodel in self._inprogress_models:
            wfmodel: Workflow


class SimStackServer(object):
    def __init__(self, my_executable):
        self._config : Config = None
        if self._register(my_executable):
            raise AlreadyRunningException("Already running, please discard silently.")
        self._logger = logging.getLogger("SimStackServer")

    def _register(self, my_executable):
        self._config = Config()
        if self._config.is_running():
            return False

        self._config.register_pid()
        # Workblock start
        try:
            me = my_executable
            # We register with crontab:
            self._config.register_crontab(me)

        except Exception as e:
            self._config.teardown_pid()
            raise e

    def _shutdown(self, remove_crontab = True):
        if self._config is None:
            # Something seriously went wrong here.
            raise SystemExit("Could not setup config. Exiting.")
        if remove_crontab:
            self._config.unregister_crontab()
        self._config.teardown_pid()

    @staticmethod
    def _workflow_object_from_file(filename):
        with open(filename,'rt') as infile:
            myxml = etree.parse(infile).getroot()
        a = Workflow()
        a.from_xml(myxml)
        return a

    def main_loop(self, workflow_file = None):
        work_done = False
        # Do stuff
        if workflow_file is not None:
            workflow = self._workflow_object_from_file(workflow_file)

            for i in range(0,10):
                workflow.jobloop()
                time.sleep(3)

        work_done = True
        #
        self._shutdown(remove_crontab=work_done)

    def __del__(self):
        # In any case on destruct we try to remove the PID if by some means we didn't using regular shutdown.
        if not self._config is None:
            self._config.teardown_pid()



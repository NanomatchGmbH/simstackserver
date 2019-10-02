import json
import time
from SimStackServer.MessageTypes import SSS_MESSAGETYPE as MessageTypes, Message

import zmq

from lxml import etree

import logging
import threading

#from SimStackServer import ClusterManager
from zmq.auth.thread import ThreadAuthenticator

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
        self._setup_root_logger()
        self._config : Config = None
        if not self._register(my_executable):
            raise AlreadyRunningException("Already running, please discard silently.")
        self._logger = logging.getLogger("SimStackServer")
        self._workflow_manager = WorkflowManager()
        self._zmq_context = None
        self._auth = None
        self._communication_timeout = 4.0
        self._polling_time = 500 # We check every half second for new message
        self._commthread = None
        self._stop_thread = False

    @classmethod
    def _setup_root_logger(cls):
        Config._setup_root_logger()

    @staticmethod
    def register_pidfile():
        return Config.register_pid()

    @staticmethod
    def get_appdirs():
        return Config._dirs

    def _message_handler(self, message_type, message, sock):
        if message_type == MessageTypes.CONNECT:
            #Simply acknowledge connection, no args
            self._sock.send(Message.connect_message())
        elif message_type == MessageTypes.ABORTWF:
            # Arg is associated workflow
            pass
        elif message_type == MessageTypes.LISTJOBS:
            # Arg is associated workflow
            pass
        elif message_type == MessageTypes.DELWF:
            # Arg is workflow submit name, which will be unique
            pass
        elif message_type == MessageTypes.LISTWFS:
            # No Args, returns stringlist of Workflow submit names
            pass

    def _zmq_worker_loop(self, port):
        context = self._zmq_context
        sock = context.socket(zmq.REP)
        sock.plain_server = True
        sock.bind('tcp://127.0.0.1:%s' % port)
        poller = zmq.Poller()
        poller.register(sock, zmq.POLLIN)
        while True:
            if self._stop_thread:
                self._logger.info("Terminating communication thread.")
                poller.unregister(sock)
                del poller
                sock.close()
                return
            socks = dict(poller.poll(self._polling_time))
            if sock in socks:
                messagetype, message = Message.unpack(sock.recv())
                self._message_handler(messagetype,message, sock)
            else:
                print(socks)
            print("Iter")

    def _register(self, my_executable):
        self._config = Config()
        if self._config.is_running():
            return False

        try:
            me = my_executable
            # We register with crontab:
            self._config.register_crontab(me)

            return True

        except Exception as e:
            raise e

    def setup_zmq_port(self, port, password):
        if self._zmq_context is None:
            self._zmq_context = zmq.Context()

        if self._auth is None:
            self._auth = ThreadAuthenticator(self._zmq_context)
            auth = self._auth
            auth.start()
            auth.allow('127.0.0.1')
            auth.configure_plain(domain='*', passwords={"simstack_client": password})

        if self._commthread is None:
            self._commthread = threading.Thread(target = self._zmq_worker_loop, args=(port,))
            self._commthread.start()

    def terminate(self):
        self._stop_thread = True
        time.sleep(2.0*self._polling_time/1000.0)
        if self._zmq_context is not None:
            self._zmq_context.term()

    def _shutdown(self, remove_crontab = True):
        if self._config is None:
            # Something seriously went wrong here.
            raise SystemExit("Could not setup config. Exiting.")
        if remove_crontab:
            self._config.unregister_crontab()

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
        time.sleep(10)
        self._shutdown(remove_crontab=work_done)



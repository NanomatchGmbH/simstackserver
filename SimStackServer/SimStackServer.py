import json
import os
import signal
import time
from pathlib import Path
from queue import Queue, Empty

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


"""
TODO:
SimStackServer has to have a copy of WorkflowManager
WorkflowManager should do a list of Workflows, inprogress, etc.
WorkflowManager should send the workflowmodel if request
Abort and delete are passed on to WorkflowManager
Client gets a new section, finished, inprogress
Who takes care of jobs? 
-> Workflow
"""

class WorkflowManager(object):
    def __init__(self):
        self._logger = logging.getLogger("WorkflowManager")
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

    def _get_workflows(self, which_ones):
        """
        Helper function, which prepares the workflows in the format to be communicated.
        :param which_ones (dict):
        :return (list): List of status dicts understood by client.
        """
        output = []
        for workflow in which_ones:
            workflow : Workflow
            wfdict = {
                'id': workflow.name,
                'name' : workflow.name,
                'path' : workflow.storage,
                'status': workflow.status,
                'type': 'w'
            }
            output.append(wfdict)

        return output

    def get_inprogress_workflows(self):
        return self._get_workflows(self._inprogress_models)

    def get_finished_workflows(self):
        return self._get_workflows(self._finished_models)

    def add_workflow(self, workflow_filename):
        """
        The client has just instructed us about the existence of a workflow. We have to add it here.
        :param workflow_filename (str): Path to the new file
        :return:
        """
        newwf = Workflow.new_instance_from_xml(workflow_filename)
        self._inprogress_models.append(newwf)

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

    def start_wf(self, workflow_file):
        workflow = Workflow.new_instance_from_xml(workflow_file)
        self._logger.debug("Added workflow from file %s with name %s"%(workflow_file, workflow.name))
        self._inprogress_models[workflow.name] = workflow


class SimStackServer(object):
    def __init__(self, my_executable):
        self._setup_root_logger()
        self._config : Config = None
        self._logger = logging.getLogger("SimStackServer")
        if not self._register(my_executable):
            self._logger.debug("Already running, should exit here.")
            
            raise AlreadyRunningException("Already running, please discard silently.")
        self._workflow_manager = WorkflowManager()
        self._zmq_context = None
        self._auth = None
        self._communication_timeout = 4.0
        self._polling_time = 500 # We check every half second for new message
        self._commthread = None
        self._stop_thread = False
        self._stop_main = False
        self._submitted_job_queue = Queue()

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
            sock.send(Message.connect_message())
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
        elif message_type == MessageTypes.SUBMITWF:
            self._logger.debug(message)
            sock.send(Message.ack_message())
            workflow_filename = message["filename"]
            self._submitted_job_queue.put(workflow_filename)
            #workflow = Workflow.new_instance_from_xml()
            #pass


    def _zmq_worker_loop(self, port):
        context = self._zmq_context
        sock = context.socket(zmq.REP)
        sock.plain_server = True
        sock.setsockopt(zmq.RCVTIMEO, 1000)
        sock.setsockopt(zmq.LINGER, 0)
        bindaddr = 'tcp://127.0.0.1:%s' % port
        self._logger.info("Message worker thread binding to %s."%bindaddr)
        sock.bind(bindaddr)
        poller = zmq.Poller()
        poller.register(sock, zmq.POLLIN)
        counter = 0
        while True:
            counter += 1
            if self._stop_thread:
                self._logger.info("Terminating communication thread.")
                poller.unregister(sock)
                sock.close()
                self._logger.info("Closed socket, unregistered poller.")
                return
            socks = dict(poller.poll(self._polling_time))
            if sock in socks:
                data = sock.recv()
                self._logger.debug("Received a message.")
                messagetype, message = Message.unpack(data)
                self._logger.debug("MessageType was: %s."%MessageTypes(messagetype).name)
                self._message_handler(messagetype,message, sock)
            else:
                pass
            if counter % 50 == 0:
                self._logger.debug("Socket Worker Heartbeat log")

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
            self._zmq_context = zmq.Context.instance()

        if self._auth is None:
            self._auth = ThreadAuthenticator(self._zmq_context)
            auth = self._auth
            auth.start()
            auth.allow('127.0.0.1')
            auth.configure_plain(domain='*', passwords={"simstack_client": password})
            self._logger.debug("Configured Authentication with pass %s"%password)

        if self._commthread is None:
            self._commthread = threading.Thread(target = self._zmq_worker_loop, args=(port,))
            self._commthread.start()

    def _signal_handler(self, signum, frame):
        self._logger.debug("Received signal %d. Terminating server."%signum)
        assert signum in [signal.SIGTERM, signal.SIGINT]
        self._stop_main = True
        self._stop_thread = True

    def _remote_relative_to_absolute_filename(self, infilename):
        """
        Resolves infilename to local home
        :param infilename (str): Infilename as submitted by client. i.e. either absolute /home/me/abc/def or abc/def. NOT relative to current dir, but relative to home
        :return (str): Absolute filename on cluster
        """
        if infilename.strip().startswith("/"):
            return infilename
        else:
            return os.path.join(Path.home(),infilename)

    def terminate(self):
        self._stop_thread = True
        time.sleep(2.0 * self._polling_time / 1000.0)
        if not self._auth is None:
            self._auth.stop()
        if self._zmq_context is not None:
            self._logger.debug("Terminating ZMQ context.")
            #The correct call here would be:
            # self._zmq_context.term()
            # However: term can hang and leave the Server dangling. Therefore: destory
            # I will gladly take an error message over deadlock.
            # If term ever gets a timeout argument, please switch over.
            self._zmq_context.destroy()
            self._logger.debug("ZMQ context terminated.")

    def _shutdown(self, remove_crontab = True):
        if self._config is None:
            # Something seriously went wrong here.
            raise SystemExit("Could not setup config. Exiting.")
        if remove_crontab:
            self._config.unregister_crontab()

    def main_loop(self, workflow_file = None):
        work_done = False
        # Do stuff
        if workflow_file is not None:
            workflow = Workflow.new_instance_from_xml(workflow_file)

            for i in range(0,10):
                workflow.jobloop()
                time.sleep(3)

        counter = 0
        while not self._stop_main:
            counter+=1
            if self._submitted_job_queue.empty():
                time.sleep(3)
            else:
                try:
                    tostart = self._submitted_job_queue.get(timeout = 5)
                    tostart_abs = self._remote_relative_to_absolute_filename(tostart)
                    self._logger.info("Starting workflow %s"%tostart_abs)
                    self._workflow_manager.start_wf(tostart_abs)
                except Empty as e:
                    self._logger.error("Another thread consumed a workflow from the queue, although we should be the only thread.")
            if counter % 30 == 0:
                self._logger.debug("Main Thread heartbeat")



        work_done = True
        self.terminate()
        self._shutdown(remove_crontab=work_done)

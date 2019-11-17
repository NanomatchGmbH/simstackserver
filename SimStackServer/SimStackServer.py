import json
import os
import shutil
import signal
import time
from pathlib import Path
from queue import Queue, Empty


from SimStackServer.MessageTypes import SSS_MESSAGETYPE as MessageTypes, Message, JobStatus

import zmq

from lxml import etree

import logging
import threading

#from SimStackServer import ClusterManager
from zmq.auth.thread import ThreadAuthenticator

from SimStackServer.Config import Config
from SimStackServer.Util.FileUtilities import mkdir_p
from SimStackServer.WorkflowModel import Workflow

class AlreadyRunningException(Exception):
    pass


"""
TODO:



Abort and delete are passed on to WorkflowManager
Client gets a new section, finished, inprogress
Who takes care of jobs? 
-> Workflow


Remaining problems:
- Save and Load WorkflowManager
   - Recreate jobs from jobid / only for checking
- Delete Job? Abort Job? Abort Workflow?
  - When Moving workflow, we need to save workflow
  - Abort Workflow means: move to finished, set status to aborted, all in progress jobs abort
  - Delete Workflow means: Abort workflow, then delete directory  
  - Suspend workflow?


"""


class WorkflowError(Exception):
    pass


class WorkflowManager(object):
    def __init__(self):
        self._logger = logging.getLogger("WorkflowManager")
        self._inprogress_models = {}
        self._finished_models = {}
        self._deletion_queue = Queue()

    def from_json(self, filename):
        with open(filename, 'rt') as infile:
            mydict = json.load(infile)
        inprogress = mydict["inprogress"]
        finished = mydict["finished"]
        self._recreate_models_from_filenames(inprogress,finished)

    def _recreate_models_from_filenames(self, inprogress_filenames, finished_filenames):
        for inprogress_fn in inprogress_filenames:
            self._add_workflow(inprogress_fn, self._inprogress_models)
        for finished_fn in finished_filenames:
            self._add_workflow(finished_fn, self._finished_models)

    @staticmethod
    def _parse_xml(filename):
        with open(filename,'rt') as infile:
            xml = etree.parse(infile).getroot()
        return xml

    def abort_workflow(self, workflow_submitname):
        if workflow_submitname in self._inprogress_models:
            self._inprogress_models[workflow_submitname].abort()
        else:
            self._logger.warning("Tried to abort workflow, which was not found in inprogress workflows.")

    def _get_workflows(self, which_ones):
        """
        Helper function, which prepares the workflows in the format to be communicated.
        :param which_ones (dict):
        :return (list): List of status dicts understood by client.
        """
        output = []
        for workflow in which_ones.values():
            workflow : Workflow
            wfdict = {
                'id': workflow.submit_name,
                'name' : workflow.submit_name,
                'path' : workflow.storage,
                'status': workflow.status,
                'type': 'w'
            }
            output.append(wfdict)

        return output

    def workflows_running(self):
        """
        Returns number of running workflows. The main thread can terminate if this is 0.
        :return (int): Number of running workflows.
        """
        return len(self._inprogress_models)

    def get_inprogress_workflows(self):
        return self._get_workflows(self._inprogress_models)

    def get_finished_workflows(self):
        return self._get_workflows(self._finished_models)

    def add_finished_workflow(self, workflow_filename):
        return self._add_workflow(workflow_filename, self._finished_models)

    def add_inprogress_workflow(self, workflow_filename):
        return self._add_workflow(workflow_filename, self._inprogress_models)

    def _add_workflow(self, workflow_filename, target_dict):
        """
        The client has just instructed us about the existence of a workflow. We have to add it here.
        :param workflow_filename (str): Path to the new file
        :return:
        """
        newwf = Workflow.new_instance_from_xml(workflow_filename)
        newwf: Workflow
        newwf.abs_resolve_storage()
        if newwf.submit_name in self._inprogress_models or newwf.submit_name in self._finished_models:
            errormessage = "Discarding workflow with submit_name: %s as it was already present." %newwf.submit_name
            self._logger.error(errormessage)
            raise WorkflowError(errormessage)
        target_dict[newwf.submit_name] = newwf
        return newwf

    def to_json(self, filename):
        inprogress = []
        finished = []
        for wf in self._inprogress_models.values():
            wf: Workflow
            fn = wf.get_filename()
            inprogress.append(fn)

        for wf in self._finished_models.values():
            wf: Workflow
            fn = wf.get_filename()
            finished.append(fn)

        mydict = {
            "inprogress": inprogress,
            "finished": finished
        }
        with open(filename, 'wt') as outfile:
            json.dump(mydict, outfile)

    def check_status_submit(self):
        while not self._deletion_queue.empty():
            myitem = self._deletion_queue.get()
            self._delete_workflow_and_folder(myitem)

        move_to_finished = []
        for wfsubmit_name, wfmodel in self._inprogress_models.items():
            wfmodel: Workflow
            try:
                if wfmodel.jobloop():
                    if wfmodel.status == JobStatus.ABORTED:
                        self._logger.info("Aborting all jobs of %s." % wfsubmit_name)
                        wfmodel.all_job_abort()
                    self._logger.debug("Moving %s to finished workflows"%wfsubmit_name)
                    move_to_finished.append(wfsubmit_name)
            except Exception as e:
                self._logger.exception("Uncaught exception during jobloop of workflow %s. Aborting."%wfsubmit_name)
                wfmodel.abort()
                move_to_finished.append(wfsubmit_name)


        for key in move_to_finished:
            wf = self._inprogress_models[key]
            wf: Workflow
            # We dump the finished workflow one last time.
            wf.dump_xml_to_file(wf.get_filename())
            self._finished_models[key] = self._inprogress_models[key]
            del self._inprogress_models[key]

    def list_jobs_of_workflow(self, workflow_submit_name):
        if workflow_submit_name in self._inprogress_models:
            mywf = self._inprogress_models[workflow_submit_name]
        elif workflow_submit_name in self._finished_models:
            mywf = self._finished_models[workflow_submit_name]
        else:
            self._logger.error("Could not find workflow in inprogress or finished workflows.")
            return []
        mywf: Workflow
        return mywf.get_running_finished_job_list_formatted()

    def start_wf(self, workflow_file):
        workflow = self.add_inprogress_workflow(workflow_file)
        self._logger.debug("Added workflow from file %s with submit_name %s"%(workflow_file, workflow.submit_name))

    def backup_and_save(self):
        for mywfmodel in self._inprogress_models.values():
            mywfmodel: Workflow
            mywfmodel.dump_xml_to_file(mywfmodel.get_filename())

        appdirs = SimStackServer.get_appdirs()
        mkdir_p(appdirs.user_data_dir)
        outfile = os.path.join(appdirs.user_data_dir, "workflow_manager_state.json")
        if os.path.isfile(outfile):
            shutil.move(outfile, outfile+ ".bak")
        self.to_json(outfile)

    def restore(self):
        appdirs = SimStackServer.get_appdirs()
        infile = os.path.join(appdirs.user_data_dir, "workflow_manager_state.json")
        self._logger.debug("Trying to read %s"%infile)
        if os.path.isfile(infile):
            # We only try to restore, if it's present, otherwise we try to start from backup, otherwise
            try:
                self.from_json(infile)
            except Exception as e:
                self._logger.exception("Tried to recreate workflow manager from infile, which could not be read.")
                bakfile = infile+ ".bak"
                if os.path.exists(bakfile):
                    try:
                        self._logger.info("Trying to recreate workflow info from backup config")
                        self.from_json(bakfile)
                    except Exception as e:
                        self._logger.exception("Backup config could also not be read")
        else:
            self._logger.info("Generating new workflow manager")

    def _delete_workflow_and_folder(self, workflow_submitname):
        if workflow_submitname in self._inprogress_models:
            target_dict = self._inprogress_models
        elif workflow_submitname in self._finished_models:
            target_dict = self._finished_models
        else:
            self._logger.warning("Did not find workflow in running models.")
            return
        mywf = target_dict[workflow_submitname]
        mywf: Workflow
        mywf.all_job_abort()
        mywf.delete_storage()
        # Forbid model access here
        del target_dict[workflow_submitname]
        # Release model access here

    def delete_workflow(self, workflow_submitname):
        if workflow_submitname in self._inprogress_models:
            self._inprogress_models[workflow_submitname].delete()
            self._deletion_queue.put(workflow_submitname)
        elif workflow_submitname in self._finished_models:
            self._finished_models[workflow_submitname].delete()
            self._deletion_queue.put(workflow_submitname)
        else:
            self._logger.error("Did not find workflow %s in model lists." %workflow_submitname)


class SimStackServer(object):
    def __init__(self, my_executable):
        self._setup_root_logger()
        self._config : Config = None
        self._logger = logging.getLogger("SimStackServer")
        if not self._register(my_executable):
            self._logger.debug("Already running, should exit here.")
            raise AlreadyRunningException("Already running, please discard silently.")
        self._workflow_manager = WorkflowManager()
        self._workflow_manager.restore()
        self._zmq_context = None
        self._auth = None
        self._communication_timeout = 4.0
        self._polling_time = 500 # We check every half second for new message
        self._commthread = None
        self._stop_thread = False
        self._stop_main = False
        self._submitted_job_queue = Queue()
        self._filetime_on_init = self._get_module_mtime()

    @classmethod
    def _setup_root_logger(cls):
        Config._setup_root_logger()

    @staticmethod
    def register_pidfile():
        return Config.register_pid()

    def _get_module_mtime(self):
        """
        This gets the last modification time of the data directory in the
        SimStackServer Codebase. We will use this to see, if there was an update. If
        there was, we terminate (and hope that cron revives us).
        :return (time):
        """
        import SimStackServer.Data as data
        datadir = os.path.abspath(os.path.realpath(data.__path__[0]))
        mtime = os.path.getmtime(datadir)
        return mtime

    @staticmethod
    def get_appdirs():
        return Config._dirs

    def _message_handler(self, message_type, message, sock):
        # Every message here MUST absolutely have a send after, otherwise the client will hang.
        # All code, which is not a deadfire send has to be in try except
        if message_type == MessageTypes.CONNECT:
            #Simply acknowledge connection, no args
            sock.send(Message.connect_message())

        elif message_type == MessageTypes.ABORTWF:
            # Arg is associated workflow
            sock.send(Message.ack_message())
            try:
                toabort = message["workflow_submit_name"]
                self._logger.debug("Receive workflow abort message %s" % toabort)
                self._workflow_manager.abort_workflow(toabort)
            except Exception as e:
                self._logger.exception("Error aborting workflow %s."%(toabort))

        elif message_type == MessageTypes.LISTWFJOBS:
            # Arg is associated workflow
            tolistwf = message["workflow_submit_name"]
            try:
                list_of_jobs = self._workflow_manager.list_jobs_of_workflow(tolistwf)
            except Exception as e:
                self._logger.exception("Error listing jobs of workflow %s" %tolistwf)
                list_of_jobs = []
            sock.send(Message.list_jobs_of_wf_message_reply(tolistwf,list_of_jobs))


        elif message_type == MessageTypes.DELWF:
            sock.send(Message.ack_message())
            try:
                toabort = message["workflow_submit_name"]
                self._logger.debug("Receive workflow delete message %s" % toabort)
                self._workflow_manager.abort_workflow(toabort)
                self._workflow_manager.delete_workflow(toabort)
            except Exception as e:
                self._logger.exception("Error deleting workflow %s." %toabort)

        elif message_type == MessageTypes.DELJOB:
            sock.send(Message.ack_message())
            try:
                workflow_submit_name = message["workflow_submit_name"]
                job_submit_name = message["job_submit_name"]
                self._logger.error("DELWF not implemented, however I would like to delete %s from %s"%(job_submit_name, workflow_submit_name))
            except Exception as e:
                self._logger.exception("Error during job deletion.")

        elif message_type == MessageTypes.LISTWFS:
            # No Args, returns stringlist of Workflow submit names
            try:
                self._logger.debug("Received LISTWFS message")
                workflows = self._workflow_manager.get_inprogress_workflows() + self._workflow_manager.get_finished_workflows()
            except Exception as e:
                self._logger.exception("Error listing workflows.")
                workflows = []

            sock.send(Message.list_wfs_reply_message(workflows))

        elif message_type == MessageTypes.SUBMITWF:
            sock.send(Message.ack_message())
            try:
                workflow_filename = message["filename"]
                self._logger.debug("Received SUBMITWF message, submitting %s" % workflow_filename)
                self._submitted_job_queue.put(workflow_filename)
            except Exception as e:
                self._logger.exception("Error submitting workflow.")


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
            # Note, maybe with the current setup, where we set linger on all ports this would be a non-issue.
            self._zmq_context.destroy()
            self._logger.debug("ZMQ context terminated.")
        
        #Now that nothing is running anymore, we save WorkflowManagers runtime information and all workflows (inside WFM)
        self._workflow_manager.backup_and_save()

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
        maxidleduration = 1200 # After 20 minutes idle (i.e. no running workflow and nobody doing anything) we quit.
        terminationtime = time.time() + maxidleduration
        while not self._stop_main:
            counter+=1
            timeextension = False
            #Submitted job queue
            if self._submitted_job_queue.empty():
                try:
                    self._workflow_manager.check_status_submit()
                except Exception as e:
                    self._logger.exception("Ran into problem during workflow manager loop.")
                time.sleep(3)
            else:
                try:
                    try:
                        timeextension = True
                        tostart = self._submitted_job_queue.get(timeout = 5)
                        tostart_abs = self._remote_relative_to_absolute_filename(tostart)
                        self._logger.info("Starting workflow %s"%tostart_abs)
                        self._workflow_manager.start_wf(tostart_abs)
                    except Empty as e:
                        self._logger.error("Another thread consumed a workflow from the queue, although we should be the only thread.")
                except Exception as e:
                    self._logger.exception("Exception in Workflow starting.")

            if self._workflow_manager.workflows_running() > 0:
                timeextension = True

            if timeextension:
                terminationtime = time.time() + maxidleduration

            if counter % 30 == 0:
                self._logger.debug("Main Thread heartbeat")
                # We also check whether there is an update.
                if self._get_module_mtime() != self._filetime_on_init:
                    self._logger.info("Found updated SimStackServer files. Stopping server for update.")
                    self._stop_main = True

            if time.time() > terminationtime:
                # We have been idling for maxidleduration. Terminating.
                work_done = True
                self._stop_main = True

        self.terminate()
        self._shutdown(remove_crontab=work_done)

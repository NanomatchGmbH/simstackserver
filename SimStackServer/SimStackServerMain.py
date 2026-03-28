import json
import os
import shutil
import signal
import time
from pathlib import Path
from queue import Queue, Empty


from SimStackServer.MessageTypes import JobStatus
from SimStackServer.HTTPServer.HTTPServer import CustomHTTPServerThread
from SimStackServer.FastAPIServer import FastAPIThread

from lxml import etree

import logging

from SimStackServer.Config import Config
from SimStackServer.RemoteServerManager import RemoteServerManager
from SimStackServer.SecureWaNos import SecureModeGlobal
from SimStackServer.Util.FileUtilities import mkdir_p

from SimStackServer.Util.SocketUtils import get_open_port, random_pass
from SimStackServer.WorkflowModel import Workflow, WorkflowExecModule


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


class WorkflowManager:
    def __init__(self):
        self._logger = logging.getLogger("WorkflowManager")
        self._inprogress_models = {}
        self._finished_models = {}
        self._inprogress_singlejobs = {}
        self._finished_singlejobs = {}
        self._deletion_queue = Queue()
        self._deletion_queue_singlejobs = Queue()
        self._processfarm_thread = (
            None  # This is only used if the internal batch system is to be used.
        )
        self._processfarm = None
        self._remote_servers = RemoteServerManager.get_instance()

    def from_json(self, filename):
        with open(filename, "rt") as infile:
            mydict = json.load(infile)
        inprogress = mydict["inprogress"]
        finished = mydict["finished"]
        self._recreate_models_from_filenames(inprogress, finished)

    def _recreate_models_from_filenames(self, inprogress_filenames, finished_filenames):
        for inprogress_fn in inprogress_filenames:
            try:
                self._add_workflow(inprogress_fn, self._inprogress_models)
            except WorkflowError as e:
                self._logger.exception(str(e))
        for finished_fn in finished_filenames:
            try:
                self._add_workflow(finished_fn, self._finished_models)
            except WorkflowError as e:
                self._logger.exception(str(e))

    @staticmethod
    def _parse_xml(filename):
        with open(filename, "rt") as infile:
            xml = etree.parse(infile).getroot()
        return xml

    def abort_workflow(self, workflow_submitname):
        if workflow_submitname in self._inprogress_models:
            self._inprogress_models[workflow_submitname].abort()
        else:
            self._logger.warning(
                "Tried to abort workflow, which was not found in inprogress workflows."
            )

    def abort_singlejob(self, wfem_uid: str):
        inprogress_job: WorkflowExecModule = self._inprogress_singlejobs.get(
            wfem_uid, None
        )
        if inprogress_job:
            self._logger.info(f"Aborting job with uid {wfem_uid}")
            inprogress_job.abort_job()
        else:
            jobs = ",".join(str(job) for job in self._inprogress_singlejobs.keys())
            self._logger.info(
                f"Did not find {wfem_uid} in inprogress jobs anymore. Running jobs were: {jobs}"
            )
            finished_jobs = ",".join(
                str(job) for job in self._finished_singlejobs.keys()
            )
            self._logger.info(f"Finished jobs were: {finished_jobs}.")

    def _get_workflows(self, which_ones):
        """
        Helper function, which prepares the workflows in the format to be communicated.
        :param which_ones (dict):
        :return (list): List of status dicts understood by client.
        """
        output = []
        for workflow in which_ones.values():
            workflow: Workflow
            wfdict = {
                "id": workflow.submit_name,
                "name": workflow.submit_name,
                "path": workflow.storage,
                "status": workflow.status,
                "type": "w",
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

    def _start_internal_queue(self):
        if self._processfarm_thread is None:
            self._logger.info("Starting internal batch system")
            from SimStackServer.Util.InternalBatchSystem import InternalBatchSystem

            (
                self._processfarm,
                self._processfarm_thread,
            ) = InternalBatchSystem.get_instance()
        assert (
            self._processfarm_thread.is_alive()
        ), "ProcessFarm thread not alive after starting"
        self._logger.debug("Processfarm is still alive")

    def shutdown(self):
        if self._processfarm_thread is not None:
            self._logger.info("Shutting down processfarm.")
            self._processfarm.abort()
            time.sleep(0.3)
            if self._processfarm_thread.is_alive():
                self._logger.error("Processfarm thread did not exit in time")

    def _add_workflow(self, workflow_filename, target_dict):
        """
        The client has just instructed us about the existence of a workflow. We have to add it here.
        :param workflow_filename (str): Path to the new file
        :return:
        """
        try:
            newwf = Workflow.new_instance_from_xml(workflow_filename)
        except FileNotFoundError as e:
            raise WorkflowError(
                "Workflow was not found at file <%s>. Discarding Workflow."
            ) from e
        newwf: Workflow
        newwf._abs_resolve_storage()
        if (
            newwf.submit_name in self._inprogress_models
            or newwf.submit_name in self._finished_models
        ):
            errormessage = (
                "Discarding workflow with submit_name: %s as it was already present."
                % newwf.submit_name
            )
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

        mydict = {"inprogress": inprogress, "finished": finished}
        with open(filename, "wt") as outfile:
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
                    self._logger.debug(
                        "Moving %s to finished workflows" % wfsubmit_name
                    )
                    move_to_finished.append(wfsubmit_name)
            except Exception:
                self._logger.exception(
                    "Uncaught exception during jobloop of workflow %s. Aborting."
                    % wfsubmit_name
                )
                wfmodel.abort()
                move_to_finished.append(wfsubmit_name)

        for singlejob_uuid, wfem in [*self._inprogress_singlejobs.items()]:
            wfem: WorkflowExecModule
            move_this_job_to_finished = False
            try:
                if wfem.completed_or_aborted():
                    self._logger.info(
                        f"Moving {singlejob_uuid} to finished singlejobs."
                    )
                    move_this_job_to_finished = True
            except Exception:
                self._logger.exception(
                    "Uncaught exception during jobloop of workflow %s. Aborting."
                    % wfsubmit_name
                )
                move_this_job_to_finished = True
                wfem.abort_job()
            if move_this_job_to_finished:
                self._finished_singlejobs[singlejob_uuid] = wfem
                del self._inprogress_singlejobs[singlejob_uuid]
                jobs = ",".join(str(job) for job in self._inprogress_singlejobs.keys())
                finished_jobs = ",".join(
                    str(job) for job in self._finished_singlejobs.keys()
                )
                self._logger.info(
                    f"Moving complete, after moving the singlejobs were, inprogress: {jobs}.  Finished: {finished_jobs}"
                )

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
            self._logger.error(
                "Could not find workflow in inprogress or finished workflows."
            )
            return []
        mywf: Workflow
        return mywf.get_running_finished_job_list_formatted()

    def start_wf(self, workflow_file):
        workflow = self.add_inprogress_workflow(workflow_file)
        self._logger.debug(
            "Added workflow from file %s with submit_name %s"
            % (workflow_file, workflow.submit_name)
        )

    def backup_and_save(self):
        for mywfmodel in self._inprogress_models.values():
            mywfmodel: Workflow
            mywfmodel.dump_xml_to_file(mywfmodel.get_filename())

        appdirs = SimStackServer.get_appdirs()
        mkdir_p(appdirs.user_data_dir)
        outfile = os.path.join(appdirs.user_data_dir, "workflow_manager_state.json")
        if os.path.isfile(outfile):
            shutil.move(outfile, outfile + ".bak")
        self.to_json(outfile)

    def restore(self):
        appdirs = SimStackServer.get_appdirs()
        infile = os.path.join(appdirs.user_data_dir, "workflow_manager_state.json")
        self._logger.debug("Trying to read %s" % infile)
        if os.path.isfile(infile):
            # We only try to restore, if it's present, otherwise we try to start from backup, otherwise
            try:
                self.from_json(infile)
            except Exception:
                self._logger.exception(
                    "Tried to recreate workflow manager from infile, which could not be read."
                )
                bakfile = infile + ".bak"
                if os.path.exists(bakfile):
                    try:
                        self._logger.info(
                            "Trying to recreate workflow info from backup config"
                        )
                        self.from_json(bakfile)
                    except Exception:
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
            self._logger.error(
                "Did not find workflow %s in model lists." % workflow_submitname
            )

    def start_singlejob(self, tostart: WorkflowExecModule):
        queueing_system = tostart.resources.queueing_system
        if queueing_system == "unset":
            raise NotImplementedError(
                "Single Jobs require a valid queueing system to be set"
            )

        if (
            tostart.resources.queueing_system == "Internal"
            and self._processfarm_thread is None
        ):
            self._start_internal_queue()

        self._prepare_singlejob(tostart)

        self._inprogress_singlejobs[tostart.uid] = tostart
        tostart.run_jobfile(None)

    def _prepare_singlejob(self, wfem: WorkflowExecModule) -> None:
        """Set up the execution directory for a bundle-based single job.

        Creates a job directory under the server basepath, unpacks the WaNo
        bundle, renders the WaNo, writes ``rendered_wano.yml``, and copies
        static input files so the exec command can run correctly.
        """
        import yaml
        from pathlib import Path as _Path

        from SimStackServer.Config import Config
        from SimStackServer.WaNo.WaNoModels import WaNoModelRoot
        from SimStackServer.WaNo.WaNoFactory import wano_without_view_constructor_helper
        from SimStackServer.WaNo.xml_compat import xml_file_to_spec
        from SimStackServer.WorkflowModel import Workflow

        basepath = Config.get_resources().basepath
        if not os.path.isabs(basepath):
            basepath = str(_Path.home() / basepath)

        jobdirectory = os.path.join(basepath, "singlejobs", wfem.uid)
        os.makedirs(jobdirectory, exist_ok=True)

        # Unpack WaNo bundle to inputs sub-directory
        wano_dir_root = _Path(jobdirectory) / "inputs"
        Workflow._unpack_wano_bundle(wfem, wano_dir_root)

        if not wfem.wano_xml:
            wfem.set_runtime_directory(jobdirectory)
            return

        # Load the WaNo model and render it
        xml_path = wano_dir_root / wfem.wano_xml
        if not xml_path.exists():
            wfem.set_runtime_directory(jobdirectory)
            return

        wmr = WaNoModelRoot.from_spec(
            xml_file_to_spec(xml_path), wano_dir_root=wano_dir_root
        )
        try:
            wmr.read(wano_dir_root)
        except FileNotFoundError:
            pass
        wmr = wano_without_view_constructor_helper(wmr)
        wmr.datachanged_force()
        wmr.datachanged_force()

        rendered_wano = wmr.wano_walker()
        rendered_wano = wmr.wano_walker_render_pass(
            rendered_wano,
            submitdir=None,
            flat_variable_list=None,
            input_var_db={},
            output_var_db={},
            runtime_variables=wfem.get_runtime_variables(),
        )

        with open(os.path.join(jobdirectory, "rendered_wano.yml"), "wt") as fh:
            yaml.safe_dump(rendered_wano, fh)

        # Render Jinja2 templates in the exec command (e.g. {{ wano["name"] }})
        from jinja2 import Template

        rendered_cmd = Template(wfem.exec_command, newline_sequence="\n").render(
            wano=rendered_wano
        )
        rendered_cmd = rendered_cmd.strip(" \t\n\r") + "\n"
        wfem.set_exec_command(rendered_cmd)

        # Copy static WaNo input files (from <WaNoInputFiles>) into the job dir
        for remote_file, local_file in wmr.input_files:
            src = wano_dir_root / local_file
            if src.exists():
                import shutil

                shutil.copy(str(src), os.path.join(jobdirectory, remote_file))

        wfem.set_runtime_directory(jobdirectory)

    def get_singlejob_status(self, wfem_uid: str):
        resultdict = {"status": "inprogress"}
        wfem = None
        if wfem_uid in self._inprogress_singlejobs:
            wfem = self._inprogress_singlejobs[wfem_uid]
        elif wfem_uid in self._finished_singlejobs:
            wfem = self._finished_singlejobs[wfem_uid]
        if wfem:
            if wfem.completed_or_aborted():
                resultdict = {"status": "finished"}
            else:
                resultdict = {"status": "inprogress"}
        self._logger.info("Finished_jobs:" + " ".join(self._finished_singlejobs.keys()))
        self._logger.info(
            "Inprogress Jobs:" + " ".join(self._inprogress_singlejobs.keys())
        )
        self._logger.info(f"My results: {resultdict}")
        return resultdict

    def add_aborted_singlejob(self, wfem: WorkflowExecModule):
        """
        This function is used in case a job is aborted, which did not even enter the WorkflowManager yet.
        :param wfem:
        :return:
        """
        self._finished_singlejobs[wfem.uid] = wfem


class OtherServerRegistry:
    def __init__(self):
        pass


class SimStackServer(object):
    def __init__(self, my_executable):
        self._clear_server_state()
        self._setup_root_logger()
        self._config = Config()
        self._config.load_server_config()
        self._logger = logging.getLogger("SimStackServer")
        if not self._register(my_executable):
            self._logger.debug("Already running, should exit here.")
            raise AlreadyRunningException("Already running, please discard silently.")
        self._workflow_manager = WorkflowManager()
        self._workflow_manager.restore()

        self._http_server = None

        self._http_user = None
        self._http_pass = None
        self._http_port = None

        self._fastapi_thread = None
        self._fastapi_port = None

        self._communication_timeout = 4.0
        self._stop_thread = False
        self._stop_main = False
        self._signal_termination = False
        self._filetime_on_init = self._get_module_mtime()

    def _clear_server_state(self):
        """
        This function should overwrite the server state completely and start fresh no matter the previous state.
        It should only be used for testing (except for the initial init of course.
        :return:
        """
        self._external_job_uid_to_jobid = {}
        self._submitted_workflow_queue = Queue()
        self._submitted_singlejob_queue = Queue()
        self._workflow_manager = WorkflowManager()

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

    def _start_http_server(self, directory):
        myport = get_open_port()
        mypass = random_pass()
        user = "simstack"
        self._http_server = CustomHTTPServerThread(
            ("", myport),
            directory=self._remote_relative_to_absolute_filename(directory),
        )
        self._logger.info("Starting HTTP server in directory %s" % directory)
        self._http_server.set_auth(user, mypass)
        self._http_server.start()
        return user, mypass, myport

    def _start_fastapi_server(
        self,
        host="127.0.0.1",
        port=None,
        username=None,
        password=None,
    ):
        """Start FastAPI server in background thread"""
        if self._fastapi_thread is None:
            if port is None:
                port = get_open_port()
            self._fastapi_port = port
            self._fastapi_thread = FastAPIThread(
                self, host, port, username=username, password=password
            )
            self._fastapi_thread.start()
            self._logger.info(f"FastAPI server started on {host}:{port}")
        return self._fastapi_port

    def _register(self, my_executable):
        self._config = Config()
        if self._config.is_running():
            return False
        return True

    def _signal_handler(self, signum, frame):
        self._logger.debug("Received signal %d. Terminating server." % signum)
        assert signum in [signal.SIGTERM, signal.SIGINT]
        self._stop_main = True
        self._stop_thread = True
        self._signal_termination = True

    def _remote_relative_to_absolute_filename(self, infilename):
        """
        Resolves infilename to local home
        :param infilename (str): Infilename as submitted by client. i.e. either absolute /home/me/abc/def or abc/def. NOT relative to current dir, but relative to home
        :return (str): Absolute filename on cluster
        """
        if infilename.strip().startswith("/"):
            return infilename
        else:
            return os.path.join(Path.home(), infilename)

    def terminate(self):
        self._stop_thread = True
        self._stop_main = True
        count = 0
        if self._http_server is not None:
            while self._http_server.is_alive() and count < 10:
                self._http_server.do_graceful_shutdown()
                count += 1

                if count == 1:
                    time.sleep(1.3)
                else:
                    time.sleep(0.02)
                if self._http_server.is_alive():
                    self._logger.debug("HTTP server should not be alive anymore.")
                    self._logger.debug(
                        "Stopping HTTP server thread, try %d of 10" % (count + 1)
                    )

        # Shutdown FastAPI server
        if self._fastapi_thread is not None:
            self._logger.info("Shutting down FastAPI server")
            self._fastapi_thread.shutdown()
            self._fastapi_thread.join(timeout=5.0)
            if self._fastapi_thread.is_alive():
                self._logger.warning("FastAPI thread did not terminate in time")

        # Now that nothing is running anymore, we save WorkflowManagers runtime information and all workflows (inside WFM)
        self._workflow_manager.backup_and_save()
        self._workflow_manager.shutdown()
        import threading

        numthreads = len([*threading.enumerate()])
        if numthreads > 1:
            self._logger.info(
                "Found more than one thread still running. Listing Threads:"
            )
            for thread in threading.enumerate():
                self._logger.info(f"Thread still running: {thread.name}")

    def _shutdown(self, remove_crontab=True):
        if self._config is None:
            # Something seriously went wrong here.
            raise SystemExit("Could not setup config. Exiting.")

    def main_loop(self, workflow_file=None):
        work_done = False
        secure_mode = SecureModeGlobal.get_secure_mode()
        # Do stuff
        if workflow_file is not None:
            workflow = Workflow.new_instance_from_xml(workflow_file)
            workflow.jobloop()
            return

        counter = 0
        maxidleduration = 1200  # After 20 minutes idle (i.e. no running workflow and nobody doing anything) we quit.
        terminationtime = time.time() + maxidleduration
        while not self._stop_main:
            counter += 1
            timeextension = False
            # Submitted job queue
            while not self._submitted_singlejob_queue.empty():
                try:
                    timeextension = True
                    tostart = self._submitted_singlejob_queue.get(timeout=5)
                    self._logger.info("Starting singlejob %s" % tostart)
                    self._workflow_manager.start_singlejob(tostart)
                except Exception:
                    self._logger.exception("Exception in Workflow starting.")
            if self._submitted_workflow_queue.empty():
                try:
                    self._workflow_manager.check_status_submit()
                except Exception:
                    self._logger.exception(
                        "Ran into problem during workflow manager loop."
                    )
                time.sleep(3)
            else:
                try:
                    try:
                        timeextension = True
                        tostart = self._submitted_workflow_queue.get(timeout=5)
                        tostart_abs = self._remote_relative_to_absolute_filename(
                            tostart
                        )
                        self._logger.info("Starting workflow %s" % tostart_abs)
                        self._workflow_manager.start_wf(tostart_abs)
                    except Empty:
                        self._logger.error(
                            "Another thread consumed a workflow from the queue, although we should be the only thread."
                        )
                except Exception:
                    self._logger.exception("Exception in Workflow starting.")

            if self._workflow_manager.workflows_running() > 0:
                timeextension = True

            if timeextension:
                terminationtime = time.time() + maxidleduration

            if counter % 30 == 0:
                self._logger.debug("Main Thread heartbeat")
                # We also check whether there is an update.
                if self._get_module_mtime() != self._filetime_on_init:
                    self._logger.info(
                        "Found updated SimStackServer files. Stopping server for update."
                    )
                    self._stop_main = True

            if not secure_mode and (time.time() > terminationtime):
                # We have been idling for maxidleduration. Terminating.
                self._logger.info(
                    "Server has been idle for %d minutes. Terminating server."
                    % (maxidleduration // 60)
                )
                work_done = True
                self._stop_main = True

        self.terminate()
        self._shutdown(remove_crontab=(work_done or self._signal_termination))

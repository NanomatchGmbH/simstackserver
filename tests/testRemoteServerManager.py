import os
import shutil
import time
import unittest


from os import path
from pathlib import Path

from SimStackServer.ClusterManager import ClusterManager
from SimStackServer.RemoteServerManager import RemoteServerManager
from SimStackServer.WorkflowModel import Resources, Workflow, WorkflowExecModule
from tests.test_WorkflowModel import SampleWFEM


class TestRemoteServerManager(unittest.TestCase):
    def setUp(self):
        self.resource1 = Resources(
            base_URI="localhost",
            username="unittest_testuser",
            port=22,
            basepath="simstack_workspace",
            queueing_system="Internal",
            sw_dir_on_resource="/home/strunk/software/nanomatch_v4/nanomatch",
        )
        self.resource2 = Resources(
            base_URI="nmc.nanomatch.de",
            username="unittest",
            port=37321,
            basepath="simstack_workspace",
            queueing_system="Internal",
            sw_dir_on_resource="/home/nanomatch/nanomatch",
        )
        self._input_dir = "%s/input_dirs/RemoteServerManager" % path.dirname(
            path.realpath(__file__)
        )
        self._transferdir = path.join(self._input_dir, "test_transfer_dir")
        self._transferdir_to = path.join(self._input_dir, "test_transfer_dir_to")
        self._wf_xml_loc = path.join(self._input_dir, "wf_xml.xml")
        self._comp_wf_dir = "%s/input_dirs/Complete_Workflow" % path.dirname(
            path.realpath(__file__)
        )
        self._comp_wf_loc = path.join(self._comp_wf_dir, "rendered_workflow.xml")
        self._comp_wf_dir_remote = (
            "%s/input_dirs/Complete_Workflow_Remote"
            % path.dirname(path.realpath(__file__))
        )
        self._comp_wf_loc_remote = path.join(
            self._comp_wf_dir_remote, "rendered_workflow.xml"
        )

        os.makedirs(self._transferdir_to, exist_ok=True)

    def _clear_server_state(self):
        rsm = RemoteServerManager.get_instance()
        cm: ClusterManager = rsm.server_from_resource(self.resource1)
        cm.connect_ssh_and_zmq_if_disconnected()
        cm.send_clearserverstate_message()

    def tearDown(self) -> None:
        exec_dirs = []
        exec_dirs.append(path.join(self._comp_wf_dir, "./exec_directories"))
        exec_dirs.append(
            path.join(self._comp_wf_dir, "workflow_data", "EmployeeRecord", "outputs")
        )
        exec_dirs.append(path.join(self._comp_wf_dir_remote, "./exec_directories"))
        exec_dirs.append(
            path.join(
                self._comp_wf_dir_remote, "workflow_data", "EmployeeRecord", "./outputs"
            )
        )
        for exec_dir in exec_dirs:
            if os.path.isdir(exec_dir):
                shutil.rmtree(exec_dir)

        from SimStackServer.Util.InternalBatchSystem import InternalBatchSystem

        pfarm, pfarm_thread = InternalBatchSystem.get_instance()
        pfarm.abort()

    def test_single_submit(self) -> None:
        wfem = SampleWFEM()
        rsm = RemoteServerManager()
        cm: ClusterManager = rsm.server_from_resource(self.resource1)
        cm.connect()
        com = cm._get_server_command()
        cm.connect_zmq_tunnel(com)
        cm.send_noop_message()
        cm.submit_single_job(wfem)
        cm.send_shutdown_message()

    @staticmethod
    def _wf_submit(folder, wf_xml_loc):
        wf = Workflow.new_instance_from_xml(wf_xml_loc)
        wf.set_storage(Path(folder))
        maxcounter = 20
        for counter in range(0, maxcounter + 1):
            finished = wf.jobloop()
            if finished:
                break
            time.sleep(2.0)
            print(f"jobloop number {counter}")
            if counter == maxcounter:
                raise TimeoutError("Workflow should have been finished long ago.")
        outputfile = path.join(
            folder, "workflow_data", "EmployeeRecord", "outputs", "Rocko"
        )
        assert os.path.isfile(outputfile), f"File {outputfile} has to exist."

    def test_wf_submit(self) -> None:
        return self._wf_submit(self._comp_wf_dir, self._comp_wf_loc)

    def test_wf_submit_remote_runthrough(self) -> None:
        self._wf_submit(self._comp_wf_dir_remote, self._comp_wf_loc_remote)
        rsm = RemoteServerManager.get_instance()
        cm: ClusterManager = rsm.server_from_resource(self.resource1)
        with cm.connection_context():
            cm.send_shutdown_message()

    def test_wf_submit_remote(self) -> None:
        self._clear_server_state()
        wf = Workflow.new_instance_from_xml(self._comp_wf_loc_remote)
        wf.set_storage(Path(self._comp_wf_dir_remote))
        wf.jobloop()
        time.sleep(1.2)
        myjob: WorkflowExecModule = wf.get_jobs()[0]
        should_be_running = not myjob.completed_or_aborted()
        self.assert_(
            should_be_running, "This workflow should have been running already."
        )
        time.sleep(10)
        wf.jobloop()
        should_be_over = myjob.completed_or_aborted()
        self.assert_(should_be_over, "This workflow should have been done already.")

        rsm = RemoteServerManager.get_instance()
        cm: ClusterManager = rsm.server_from_resource(self.resource1)
        with cm.connection_context():
            cm.send_shutdown_message()

    def test_wf_submit_remote_and_delete(self) -> None:
        self._clear_server_state()
        wf = Workflow.new_instance_from_xml(self._comp_wf_loc_remote)
        wf.set_storage(Path(self._comp_wf_dir_remote))
        wf.jobloop()
        myjob: WorkflowExecModule = wf.get_jobs()[0]
        time.sleep(2.2)
        should_be_running = not myjob.completed_or_aborted()
        self.assert_(
            should_be_running, "This workflow should have been running already."
        )
        myjob.abort_job()
        wf.jobloop()
        should_be_over = myjob.completed_or_aborted()
        self.assert_(should_be_over, "This workflow should have been done already.")

        rsm = RemoteServerManager.get_instance()
        cm: ClusterManager = rsm.server_from_resource(self.resource1)
        with cm.connection_context():
            cm.send_shutdown_message()

    def test_transfer_directory(self) -> None:
        rsm = RemoteServerManager()
        cm: ClusterManager = rsm.server_from_resource(self.resource1)
        cm.connect()
        todir = "unittest_files"
        cm.put_directory(self._transferdir, todir)
        cm.get_directory(todir, self._transferdir_to)
        cm.delete_file(f"{todir}/file1")
        cm.delete_file(f"{todir}/subdir1/subdir2/file2")

    def test_connect(self) -> None:
        rsm = RemoteServerManager()
        cm: ClusterManager = rsm.server_from_resource(self.resource1)
        cm.connect()
        com = cm._get_server_command()
        cm.connect_zmq_tunnel(com)
        cm.send_noop_message()
        cm.send_jobstatus_message("abcd")
        cm.send_abortsinglejob_message("abcd")
        time.sleep(2)
        cm.send_shutdown_message()

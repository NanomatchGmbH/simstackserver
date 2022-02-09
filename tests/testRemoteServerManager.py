import os
import shutil
import sys
import time
import unittest


from os import path
from pathlib import Path

from SimStackServer.ClusterManager import ClusterManager
from SimStackServer.RemoteServerManager import RemoteServerManager
from SimStackServer.Util.FileUtilities import file_to_xml
from SimStackServer.WorkflowModel import Resources, Workflow
from tests.testWorkflowModel import SampleWFEM


class TestRemoteServerManager(unittest.TestCase):
    def setUp(self):
        self.resource1 = Resources(base_URI="localhost",
                              username="unittest_testuser",
                              port=22,
                              basepath="simstack_workspace",
                              queueing_system="Internal",
                              sw_dir_on_resource="/home/strunk/software/nanomatch_v4/nanomatch",
        )
        self.resource2 = Resources(base_URI="nmc.nanomatch.de",
                              username="unittest",
                              port=37321,
                              basepath="simstack_workspace",
                              queueing_system="Internal",
                              sw_dir_on_resource="/home/nanomatch/nanomatch",
        )
        self._input_dir = "%s/input_dirs/RemoteServerManager" % path.dirname(path.realpath(__file__))
        self._transferdir = path.join(self._input_dir,"test_transfer_dir")
        self._transferdir_to = path.join(self._input_dir,"test_transfer_dir_to")
        self._wf_xml_loc = path.join(self._input_dir, "wf_xml.xml")
        self._comp_wf_dir = "%s/input_dirs/Complete_Workflow" % path.dirname(path.realpath(__file__))
        self._comp_wf_loc = path.join(self._comp_wf_dir, "rendered_workflow.xml")
        self._comp_wf_dir_remote = "%s/input_dirs/Complete_Workflow_Remote" % path.dirname(path.realpath(__file__))
        self._comp_wf_loc_remote = path.join(self._comp_wf_dir_remote, "rendered_workflow.xml")

        os.makedirs(self._transferdir_to, exist_ok=True)

    def tearDown(self) -> None:
        exec_dir1 = path.join(self._comp_wf_dir, "./exec_directories")
        exec_dir2 = path.join(self._comp_wf_dir_remote, "./exec_directories")
        possible_exec_dirs = [exec_dir1, exec_dir2]
        for exec_dir in possible_exec_dirs:
            if os.path.isdir(exec_dir):
                shutil.rmtree(exec_dir)

    def test_single_submit(self)-> None:
        wfem = SampleWFEM()
        rsm = RemoteServerManager()
        cm : ClusterManager = rsm.server_from_resource(self.resource1)
        cm.connect()
        com = cm._get_server_command()
        cm.connect_zmq_tunnel(com)
        cm.send_noop_message()
        cm.submit_single_job(wfem)
        time.sleep(20)
        cm.send_shutdown_message()

    def test_wf_submit(self) -> None:
        wf = Workflow.new_instance_from_xml(self._comp_wf_loc)
        wf.set_storage(Path(self._comp_wf_dir))
        wf.jobloop()

    def test_wf_submit_remote(self) -> None:
        wf = Workflow.new_instance_from_xml(self._comp_wf_loc_remote)
        wf.set_storage(Path(self._comp_wf_dir_remote))
        wf.jobloop()

    def test_transfer_directory(self) -> None:
        rsm = RemoteServerManager()
        cm: ClusterManager = rsm.server_from_resource(self.resource1)
        cm.connect()
        todir = "unittest_files"
        cm.put_directory(self._transferdir, todir)
        cm.get_directory(todir, self._transferdir_to )
        cm.delete_file(f"{todir}/file1")
        cm.delete_file(f"{todir}/subdir1/subdir2/file2")

    def test_connect(self) -> None:
        rsm = RemoteServerManager()
        cm : ClusterManager = rsm.server_from_resource(self.resource1)
        cm.connect()
        com = cm._get_server_command()
        cm.connect_zmq_tunnel(com)
        cm.send_noop_message()
        time.sleep(2)
        cm.send_shutdown_message()


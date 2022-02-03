import os
import sys
import time
import unittest


from os import path

from SimStackServer.ClusterManager import ClusterManager
from SimStackServer.RemoteServerManager import RemoteServerManager
from SimStackServer.WorkflowModel import Resources
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
    def tearDown(self) -> None:
        pass

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

    def test_connect(self) -> None:
        rsm = RemoteServerManager()
        cm : ClusterManager = rsm.server_from_resource(self.resource1)
        cm.connect()
        com = cm._get_server_command()
        cm.connect_zmq_tunnel(com)
        cm.send_noop_message()
        time.sleep(2)
        cm.send_shutdown_message()


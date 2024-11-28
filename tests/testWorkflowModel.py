import copy
import logging
import os
import pathlib
import shutil
import tempfile
import unittest
import numpy as np
from os import path
from os.path import join
from shutil import rmtree

from io import StringIO

from lxml import etree

from SimStackServer.Util import ClusterSettings
from SimStackServer.Util.FileUtilities import mkdir_p, file_to_xml
from SimStackServer.WorkflowModel import (
    Resources,
    WorkflowExecModule,
    WorkflowElementList,
    DirectedGraph,
    Workflow,
    StringList,
)


def SampleWFEM():
    xml = """    <WorkflowExecModule id="0" type="WorkflowExecModule" uid="653895b9-4a4b-4a14-b2ca-ba7aaf12e8f6" given_name="EmployeeRecord" path="EmployeeRecord" wano_xml="EmployeeRecord.xml" outputpath="EmployeeRecord">
  <inputs>
    <Ele_2 id="2" type="StringList">
      <Ele_0 id="0" type="str">test.png</Ele_0>
      <Ele_1 id="1" type="str">workflow_data/EmployeeRecord/inputs/test.png</Ele_1>
    </Ele_2>
  </inputs>
  <outputs>
    <Ele_0 id="0" type="StringList">
      <Ele_0 id="0" type="str">test</Ele_0>
      <Ele_1 id="1" type="str">test</Ele_1>
    </Ele_0>
  </outputs>
  <exec_command>touch test</exec_command>
  <resources walltime="86399" cpus_per_node="1" nodes="1" memory="4096">
    <queue>None</queue>
    <host>localhost</host>
    <custom_requests>None</custom_requests>
  </resources>
  <runtime_directory>/home/unittest_testuser/simstack_workspace/2022-02-01-15h43m23s-rmo/exec_directories/2022-02-01-15h43m23s-EmployeeRecord</runtime_directory>
  <jobid>0</jobid>
  <queueing_system>Internal</queueing_system>
</WorkflowExecModule>
"""
    test_xml = etree.parse(StringIO(xml)).getroot()
    wfem = WorkflowExecModule()
    wfem.from_xml(test_xml)
    return wfem


def test_wfem_variables():
    wfem = WorkflowExecModule()
    vars = wfem._get_mamba_variables()
    print(vars)


class TestWorkflowModel(unittest.TestCase):
    def setUp(self):
        logging.basicConfig(level=logging.DEBUG)
        self._input_dir = "%s/input_dirs/WorkflowModel" % path.dirname(
            path.realpath(__file__)
        )
        self._exec_dir = "%s/exec_dirs/WorkflowModel" % path.dirname(
            path.realpath(__file__)
        )
        self._cluster_settings_test_dir = (
            "%s/exec_dirs/ClusterSettingsTestDir"
            % path.dirname(path.realpath(__file__))
        )
        self._cluster_settings_test_dir_to = (
            "%s/exec_dirs/ClusterSettingsTestDirTo"
            % path.dirname(path.realpath(__file__))
        )
        mkdir_p(self._exec_dir)

    def tearDown(self):
        rmtree(self._exec_dir)

    def test_write_to_permanent(self):
        pass

    def sample_resource_model(self):
        example_resource_xml_fn = join(self._input_dir, "resources.xml")
        myxml = file_to_xml(example_resource_xml_fn)
        resources = Resources()
        resources.from_xml(myxml)
        return resources

    def test_sample_wfem_roundtrip(self):
        wfem = SampleWFEM()
        wfem_dict = {}
        wfem.to_dict(wfem_dict)
        wfem2 = WorkflowExecModule()
        wfem2.from_dict(wfem_dict)
        for mi in wfem.inputs:
            print(mi)
        assert wfem.inputs.compare_with_other_list(wfem2.inputs)
        # assert wfem.inputs == wfem2.inputs

    def testResourceModel(self):
        """
        This is the test xml:
            <Resources walltime="3600" cpus_per_node="32" nodes="4" memory="65536">
                <queue>not-default</queue>
                <host>superhost</host>
            </Resources>
        """

        example_resource_xml_fn = join(self._input_dir, "resources.xml")
        print(example_resource_xml_fn)
        myxml = file_to_xml(example_resource_xml_fn)

        resources = Resources()
        resources.from_xml(myxml)

        self.assertEqual(resources.walltime, 3600)
        self.assertEqual(resources.cpus_per_node, 32)
        self.assertEqual(resources.nodes, 4)
        self.assertEqual(resources.memory, 65536)
        self.assertEqual(resources.queue, "not-default")
        self.assertEqual(resources.custom_requests, "GPU=3")
        self.assertEqual(resources.username, "MaxPower")

        res = etree.Element("Resources")
        resources.to_xml(res)

        outstring = '<Resources walltime="3600" cpus_per_node="32" nodes="4" memory="65536"><queue>not-default</queue><host>superhost</host><custom_requests>GPU=3</custom_requests><base_URI></base_URI><port>0</port><username>MaxPower</username><basepath></basepath><queueing_system>pbs</queueing_system><sw_dir_on_resource></sw_dir_on_resource><extra_config>None Required (default)</extra_config><ssh_private_key>UseSystemDefault</ssh_private_key></Resources>'
        otheroutstring = etree.tostring(res).decode()

        self.assertEqual(outstring, otheroutstring)

        resdict = {}
        resources.to_dict(resdict)

        other_resource = Resources()
        other_resource.from_dict(resdict)

        other_resource_2 = Resources()
        with tempfile.NamedTemporaryFile("wt") as outfile:
            resources.to_json(pathlib.Path(outfile.name))
            other_resource_2.from_json(pathlib.Path(outfile.name))

        for oo in [other_resource_2, other_resource]:
            self.assertEqual(resources.walltime, oo.walltime)
            self.assertEqual(resources.cpus_per_node, oo.cpus_per_node)
            self.assertEqual(resources.nodes, oo.nodes)
            self.assertEqual(resources.memory, oo.memory)
            self.assertEqual(resources.queue, oo.queue)

    def _assert_resource_equal(self, rs1, rs2):
        self.assertEqual(rs1.walltime, rs2.walltime)
        self.assertEqual(rs1.cpus_per_node, rs2.cpus_per_node)
        self.assertEqual(rs1.nodes, rs2.nodes)
        self.assertEqual(rs1.memory, rs2.memory)
        self.assertEqual(rs1.host, rs2.host)
        self.assertEqual(rs1.queue, rs2.queue)

    def testClusterSettings(self):
        example_resource_xml_fn = join(self._input_dir, "resources.xml")
        print(example_resource_xml_fn)
        myxml = file_to_xml(example_resource_xml_fn)

        resources = Resources()
        resources.from_xml(myxml)

        resource2 = copy.deepcopy(resources)

        resource3 = copy.deepcopy(resources)

        outdict = {"hank": resources, "frank": resource2, "tank": resource3}
        from_folder = pathlib.Path(self._cluster_settings_test_dir)
        myset = ClusterSettings.get_cluster_settings_from_folder(from_folder)

        for name in outdict.keys():
            self._assert_resource_equal(myset[name], outdict[name])

        to_folder = pathlib.Path(self._cluster_settings_test_dir_to)
        if to_folder.is_dir():
            shutil.rmtree(to_folder)
        os.makedirs(to_folder, exist_ok=False)
        ClusterSettings.save_cluster_settings_to_folder(to_folder, myset)

        last_dict = ClusterSettings.get_cluster_settings_from_folder(to_folder)
        for name in outdict.keys():
            self._assert_resource_equal(last_dict[name], outdict[name])

    def testDigraphTravseral(self):
        ooommmm = DirectedGraph([("0", 3), (3, [4444, 983]), (983, 12)])
        ooommmm.traverse()
        outnodes = ooommmm.get_next_ready()
        print(outnodes)
        ooommmm.start(outnodes[0])
        started = outnodes[0]
        outnodes = ooommmm.get_next_ready()
        assert len(outnodes) == 0
        ooommmm.finish(started)
        outnodes = ooommmm.get_next_ready()
        print(outnodes)
        self.assertListEqual(outnodes, [4444, 983])

        ooommmm.start(4444)
        ooommmm.finish(4444)

        outnodes = ooommmm.get_next_ready()
        assert outnodes[0] == 983

        ooommmm.start(983)

        outnodes = ooommmm.get_next_ready()
        assert len(outnodes) == 0
        ooommmm.finish(983)

        outnodes = ooommmm.get_next_ready()
        self.assertListEqual(outnodes, [12])

        ooommmm.start(12)

        outnodes = ooommmm.get_next_ready()
        assert len(outnodes) == 0

        ooommmm.finish(12)
        outnodes = ooommmm.get_next_ready()
        assert len(outnodes) == 0
        for node in ooommmm.report_order_generator():
            print(node)

    def testWorkflow(self):
        myworkflow = join(self._input_dir, "rendered_workflow.xml")
        with open(myworkflow, "rt") as infile:
            myxml = etree.parse(infile).getroot()
        a = Workflow()
        a.from_xml(myxml)
        a.jobloop()

    def test_build_wf(self):
        WorkflowExecModule()

    def test_time_from_seconds_to_clusterjob_timestring(self):
        mytime = 5 * 86400 + 3 * 3600 + 12 * 60 + 14
        outstring = WorkflowExecModule._time_from_seconds_to_clusterjob_timestring(
            mytime
        )
        self.assertEqual(outstring, "5-3:12:14")
        mytime = 5
        outstring = WorkflowExecModule._time_from_seconds_to_clusterjob_timestring(
            mytime
        )
        self.assertEqual(outstring, "05")
        mytime = 2 * 60 + 4
        outstring = WorkflowExecModule._time_from_seconds_to_clusterjob_timestring(
            mytime
        )
        self.assertEqual(outstring, "02:04")

    def testWorkflowElement(self):
        a = WorkflowExecModule()
        test_xml_str = """
        <TestWFE>
            <resources walltime="5" cpus_per_node="3" nodes="12" memory="1644">
                <queue>ault</queue>
                <host>host</host>
            </resources>
        </TestWFE>
        """
        test_xml = etree.parse(StringIO(test_xml_str)).getroot()
        parent_dict = {}
        import pprint

        a.to_dict(parent_dict)
        pprint.pprint(parent_dict)

        myxml = etree.Element("TestWFE")
        a.to_xml(myxml)
        print(etree.tostring(myxml, pretty_print=True).decode())

        b = WorkflowExecModule()
        b.from_xml(test_xml)
        otherdict = {}
        b.to_dict(otherdict)
        pprint.pprint(otherdict)

        c = WorkflowExecModule()
        c.from_dict(otherdict)

        outoutdict = {}
        c.to_dict(outoutdict)
        pprint.pprint(outoutdict)

        myxml = etree.Element("TestWFEL")

        d = WorkflowElementList()
        d._add_to_list("np.int64", np.int64(4.0))
        d.to_xml(myxml)
        ddict = {}
        d.to_dict(ddict)
        pprint.pprint(ddict)
        e = WorkflowElementList()
        e.from_xml(myxml)

        f = WorkflowElementList()
        f.from_dict(ddict)

        roundtrip_dict = {}
        f.to_dict(roundtrip_dict)
        pprint.pprint(roundtrip_dict)
        print(etree.tostring(myxml, pretty_print=True).decode())

        ooooo = Resources(walltime=101)
        assert ooooo.walltime == 101
        h = WorkflowExecModule(resources=Resources(walltime=201))
        print(h.resources.walltime)
        assert h.resources.walltime == 201

        outor = {}
        oik = WorkflowElementList(
            [("WorkflowExecModule", h), ("WorkflowExecModule", h)]
        )
        oik.to_dict(outor)
        pprint.pprint(outor)

        oik_xml = etree.Element("WFEM")
        oik.to_xml(oik_xml)
        print(outor)
        print(etree.tostring(oik_xml, encoding="utf8", pretty_print=True).decode())

        ooommmm = DirectedGraph([(3, [4444, 983]), (983, 12)])

        test_xml = etree.Element("DiGraph")
        print(ooommmm.to_xml(test_xml))
        print(etree.tostring(test_xml, pretty_print=True).decode())
        for hild in test_xml:
            assert hild.tag == "{http://graphml.graphdrawing.org/xmlns}graphml"
        ooommmm.from_xml(test_xml)
        outtest = {}
        ooommmm.to_dict(outtest)
        ooommmm.from_dict(outtest)

        test_xml = etree.Element("Workflow")
        ab = Workflow(elements=oik, graph=ooommmm)

        ab.to_xml(test_xml)
        print(etree.tostring(test_xml, encoding="utf8", pretty_print=True).decode())

        test_xml = etree.Element("StringList")
        ab = StringList(["aaa", "abbb"])
        ab.to_xml(test_xml)
        print(etree.tostring(test_xml, encoding="utf8", pretty_print=True).decode())

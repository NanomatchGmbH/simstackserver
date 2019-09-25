import logging
import unittest
import numpy as np
from os import path
from os.path import join
from shutil import rmtree

from io import StringIO

from lxml import etree

from SimStackServer.Util.FileUtilities import mkdir_p, file_to_xml
from SimStackServer.WorkflowModel import Resources, WorkflowExecModule, WorkflowElementList, DirectedGraph, Workflow, \
    StringList


class TestWorkflowModel(unittest.TestCase):
    def setUp(self):
        logging.basicConfig(level=logging.DEBUG)
        self._input_dir = "%s/input_dirs/WorkflowModel" % path.dirname(path.realpath(__file__))
        self._exec_dir = "%s/exec_dirs/WorkflowModel" % path.dirname(path.realpath(__file__))
        mkdir_p(self._exec_dir)


    def tearDown(self):
        rmtree(self._exec_dir)

    def test_write_to_permanent(self):
        pass

    def testResourceModel(self):
        """
        This is the test xml:
            <Resources walltime="3600" cpus_per_node="32" nodes="4" memory="65536">
                <queue>not-default</queue>
                <host>superhost</host>
            </Resources>
        """

        example_resource_xml_fn = join(self._input_dir,"resources.xml")
        myxml = file_to_xml(example_resource_xml_fn)


        fn = join(self._exec_dir,"resource_model")

        resources = Resources()
        resources.from_xml(myxml)

        self.assertEqual(resources.walltime, 3600)
        self.assertEqual(resources.cpus_per_node, 32)
        self.assertEqual(resources.nodes, 4)
        self.assertEqual(resources.memory, 65536)
        self.assertEqual(resources.host, "superhost")
        self.assertEqual(resources.queue, "not-default")

        res = etree.Element("Resources")
        resources.to_xml(res)


        outstring = '<Resources walltime="3600" cpus_per_node="32" nodes="4" memory="65536"><queue>not-default</queue><host>superhost</host></Resources>'
        self.assertEqual(outstring, etree.tostring(res).decode())

        resdict = {}
        resources.to_dict(resdict)

        other_resource = Resources()
        other_resource.from_dict(resdict)

        self.assertEqual(resources.walltime, other_resource.walltime)
        self.assertEqual(resources.cpus_per_node, other_resource.cpus_per_node)
        self.assertEqual(resources.nodes, other_resource.nodes)
        self.assertEqual(resources.memory, other_resource.memory)
        self.assertEqual(resources.host, other_resource.host)
        self.assertEqual(resources.queue, other_resource.queue)



    def testDigraphTravseral(self):
        ooommmm = DirectedGraph([(3,[4444,983]),(983,12)])
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
        self.assertListEqual(outnodes,[4444,983])

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

    def testWorkflow(self):
        myworkflow = join(self._input_dir, "rendered_workflow.xml")
        with open(myworkflow,'rt') as infile:
            myxml = etree.parse(infile).getroot()
        a = Workflow()
        a.from_xml(myxml)
        a.jobloop()


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
        d.add_to_list("np.int64", np.int64(4.0))
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
        print(etree.tostring(myxml,pretty_print=True).decode())

        ooooo = Resources(walltime=101)
        assert ooooo.walltime == 101
        h = WorkflowExecModule(resources = Resources(walltime = 201))
        print(h.resources.walltime)
        assert h.resources.walltime == 201

        outor = {}
        oik = WorkflowElementList([("WorkflowExecModule",h),("WorkflowExecModule",h)])
        oik.to_dict(outor)
        pprint.pprint(outor)

        oik_xml = etree.Element("WFEM")
        oik.to_xml(oik_xml)
        print(outor)
        print(etree.tostring(oik_xml,encoding="utf8",pretty_print=True).decode())

        ooommmm = DirectedGraph([(3,[4444,983]),(983,12)])

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
        ab = Workflow(elements = oik, graph = ooommmm)

        ab.to_xml(test_xml)
        print(etree.tostring(test_xml, encoding="utf8", pretty_print=True).decode())


        test_xml = etree.Element("StringList")
        ab = StringList(["aaa","abbb"])
        ab.to_xml(test_xml)
        print(etree.tostring(test_xml, encoding="utf8", pretty_print=True).decode())
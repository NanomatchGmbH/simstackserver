import os
import unittest


from os import path

from pathlib import Path

from lxml import etree

from TreeWalker.TreeWalker import TreeWalker
from SimStackServer.WaNo.WaNoFactory import wano_constructor_helper, wano_without_view_constructor_helper
from SimStackServer.WaNo.WaNoModels import WaNoItemFloatModel, WaNoModelRoot
from SimStackServer.WaNo.WaNoTreeWalker import ViewCollector, PathCollector, subdict_skiplevel, WaNoTreeWalker


def subdict_view(subdict,
                      call_info):
    newsubdict = None
    try:
        newsubdict = subdict["content"]
    except KeyError as e:
        pass
    try:
        newsubdict = subdict["TABS"]
    except KeyError as e:
        pass

    if newsubdict is not None:
        pvf = call_info["path_visitor_function"]
        svf = call_info["subdict_visitor_function"]
        dvf = call_info["data_visitor_function"]
        tw = TreeWalker(newsubdict)
        return tw.walker(capture = True, path_visitor_function=pvf,
                  subdict_visitor_function=svf,
                  data_visitor_function=dvf
        )
    return None




class TestWaNoModels(unittest.TestCase):
    def setUp(self):

        self.deposit_dir = "%s/inputs/wanos/Deposit" % path.dirname(path.realpath(__file__))
        self.depxml = path.join(self.deposit_dir,"Deposit3.xml")

        self.lf_dir = "%s/inputs/wanos/lightforge2" % path.dirname(path.realpath(__file__))
        self.lfxml = path.join(self.lf_dir, "lightforge2.xml")

        self.lf_rendered_dir = "%s/inputs/wanos/rendered_lightforge2" % path.dirname(path.realpath(__file__))
        self.lf_rendered_xml = path.join(self.lf_rendered_dir, "lightforge2.xml")

        self.qp_dir = "%s/inputs/wanos/QuantumPatch3" % path.dirname(path.realpath(__file__))
        self.qpxml = path.join(self.qp_dir, "QuantumPatch3.xml")

    def tearDown(self) -> None:
        pass

    def test_WaNoItemFloatModel(self):
        myfloatmodel = WaNoItemFloatModel(bypass_init = True)
        outdict = {}
        myfloatmodel.model_to_dict(outdict)

    def test_read_rendered_lf_wano(self):
        wmr = WaNoModelRoot(wano_dir_root=self.lf_rendered_dir, model_only=True, explicit_xml=self.lf_rendered_xml)
        wmr.read(Path(self.lf_rendered_dir))
        assert wmr.get_value("TABS.general.particle_types.electrons").get_data() is True

    def test_rendered_wano(self):
        wmr = self._construct_wano_nogui(self.qpxml)
        wmr: WaNoModelRoot
        wmr.datachanged_force()
        wmr.datachanged_force()
        rendered_wano = wmr.wano_walker()
        # We do two render passes, in case the rendering reset some values:
        fvl = []

        delta_dict = {
            "Tabs":{
                "General": {
                    "General Settings":
                        {
                            "Charge Damping": 200020.032
                        }
                }
            }
        }

        rendered_wano = wmr.wano_walker_render_pass(rendered_wano,submitdir=None,flat_variable_list=None,
                    input_var_db = None,
                    output_var_db = None,
                    runtime_variables = None
        )

        command_dict = {
            "Tabs.Shells.Outer Shells" : 4
        }
        wmr.apply_delta_dict(command_dict)
        wmr.apply_delta_dict(delta_dict)
        print(wmr.get_changed_paths())
        print(wmr.get_changed_command_paths())

    def _construct_wano_nogui(self,wanofile):
        with open(wanofile, 'rt') as infile:
            xml = etree.parse(infile)
        wano_dir_root = Path(os.path.dirname(os.path.realpath(wanofile)))

        #MODELROOTDIRECT
        wmr = WaNoModelRoot(wano_dir_root = wano_dir_root, model_only=True, explicit_xml=wanofile)
        wmr.parse_from_xml(xml)
        wmr = wano_without_view_constructor_helper(wmr)
        outdict = {}
        wmr.model_to_dict(outdict)

        tw = TreeWalker(outdict)
        secondoutdict = tw.walker(capture = True, path_visitor_function=None, subdict_visitor_function=None, data_visitor_function=None)

        self.assertDictEqual(outdict, secondoutdict)
        thirdoutdict = tw.walker(capture=True, path_visitor_function=None, subdict_visitor_function=subdict_skiplevel,
                                 data_visitor_function=None)

        pc = PathCollector()
        tw = TreeWalker(thirdoutdict)
        tw.walker(path_visitor_function=pc.assemble_paths,
                  subdict_visitor_function=None,
                  data_visitor_function=None)
        wanopaths = wmr.get_all_variable_paths()
        wanotypes = wmr.get_paths_and_type_dict_aiida()
        self.assertListEqual(pc.paths, wanopaths)
        return wmr

    def test_dep_secure_schema(self):
        mywano : WaNoModelRoot = self._construct_wano_nogui(self.depxml)
        with open("deposit_secureschema.json",'wt') as outfile:
            outfile.write(mywano.get_secure_schema())

    def test_dep_nogui(self):
        mywano : WaNoModelRoot = self._construct_wano_nogui(self.depxml)
        print(mywano.get_secure_schema())

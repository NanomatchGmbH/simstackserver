""" Tests for calculations

"""
import os
from os import path
from os.path import join

from aiida import orm
from aiida.engine import run_get_node
from aiida.plugins import ParserFactory
from lxml import etree
from wano_calcjob.calculations import clean_dict_for_aiida
from wano_calcjob.WaNoCalcJobBase import WaNoCalcJob
from wano_calcjob.parsers import WaNoCalcJobParser

from SimStackServer.WaNo.WaNoFactory import wano_without_view_constructor_helper
from . import TEST_DIR

def depdir():
    deposit_dir = "%s/inputs/wanos/Deposit" % path.dirname(path.realpath(__file__))
    return deposit_dir

def dep_inputs():
    deposit_file_dir = "%s/input_files/" % path.dirname(path.realpath(__file__))
    moleculepdb = join(deposit_file_dir, "molecule_0.pdb")
    moleculespf = join(deposit_file_dir, "molecule_0.spf")
    return moleculepdb, moleculespf


def depxml():
    depxml = path.join(depdir(), "Deposit3.xml")
    return depxml

from SimStackServer.WaNo.WaNoModels import WaNoModelRoot

def get_parsed_dep_xml():
    wmr = WaNoModelRoot(wano_dir_root=depdir(), model_only=True)
    with open(depxml(), 'rt') as infile:
        xml = etree.parse(infile)
    wmr.parse_from_xml(xml)
    wmr = wano_without_view_constructor_helper(wmr)
    mol, spf  = dep_inputs()
    wmr["TABS"]["Molecules"]["Molecules"][0]["Molecule"].set_data(mol)
    wmr["TABS"]["Molecules"]["Molecules"][0]["Forcefield"].set_data(spf)
    wmr.datachanged_force()
    wmr.datachanged_force()
    # I don't think we need these two walks here. They are here, because legacy applications required them
    rendered_wano = wmr.wano_walker()
    wmr.wano_walker_render_pass(rendered_wano, submitdir=None, flat_variable_list=None,
                                                input_var_db=None,
                                                output_var_db=None,
                                                runtime_variables=None
    )
    rendered_wano = wmr.get_valuedict_with_aiida_types()
    return rendered_wano

def test_clean_aiida_dict():
    rendered_wano = get_parsed_dep_xml()
    outdict = clean_dict_for_aiida(rendered_wano)
    print(outdict)

def test_process(wano_code, generate_parser):
    """Test running a calculation
    note this does not test that the expected outputs are created of output parsing"""
    from aiida.plugins import DataFactory, CalculationFactory
    from aiida.engine import run

    rendered_wano = get_parsed_dep_xml()
    outdict = clean_dict_for_aiida(rendered_wano)
    print(wano_code)

    # set up calculation
    inputs = {
        'code': wano_code,
        'metadata': {
            'options': {
                'max_wallclock_seconds': 30
            },
        }
    }
    inputs.update(outdict)

    result = run_get_node(CalculationFactory('wano'), **inputs)
    myparser = WaNoCalcJobParser(result.node)
    myparser.parse_from_node(result.node)
    print("here")

    #computed_diff = result['wano'].get_content()

    #assert 'content1' in computed_diff

    #assert 'content2' in computed_diff

def test_wano_namespace_conversion():
    wmr = WaNoCalcJob._parse_wano_xml(depxml())
    namespaces = WaNoCalcJob._wano_to_namespaces_and_vars(wmr)
    print(namespaces)
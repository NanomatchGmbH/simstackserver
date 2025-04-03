""" Tests for calculations

"""
import os
from os import path
from os.path import join
from pathlib import Path

import yaml
from aiida import orm
from aiida.engine import run_get_node
from lxml import etree
from wano_calcjob.WaNoCalcJobBase import WaNoCalcJob, clean_dict_for_aiida
from wano_calcjob.calculations import Deposit3CalcJob, Deposit3Parser, EmissionCalcJob

from SimStackServer.WaNo.WaNoFactory import wano_without_view_constructor_helper


def depdir():
    deposit_dir = "%s/inputs/wanos/Deposit" % path.dirname(path.realpath(__file__))
    return deposit_dir


def emdir():
    return os.path.dirname(emxml())


def dep_inputs():
    deposit_file_dir = "%s/input_files/" % path.dirname(path.realpath(__file__))
    moleculepdb = join(deposit_file_dir, "molecule_0.pdb")
    moleculespf = join(deposit_file_dir, "molecule_0.spf")
    return moleculepdb, moleculespf


def depxml():
    return Deposit3CalcJob._myxml


def emxml():
    emxml = EmissionCalcJob._myxml
    return emxml


from SimStackServer.WaNo.WaNoModels import WaNoModelRoot


def get_parsed_em_xml():
    wmr = WaNoModelRoot(wano_dir_root=Path(emdir()), model_only=True)
    with open(emxml(), "rt") as infile:
        xml = etree.parse(infile)
    wmr.parse_from_xml(xml)
    wmr = wano_without_view_constructor_helper(wmr)
    mol, spf = dep_inputs()
    wmr["TABS"]["Molecules"]["Molecules"][0]["Molecule"].set_data(mol)
    wmr["TABS"]["Molecules"]["Molecules"][0]["Forcefield"].set_data(spf)
    wmr.datachanged_force()
    wmr.datachanged_force()

    aiida_files_by_relpath = {}
    infiles = {mol: "molecule_0.pdb", spf: "molecule_0.spf"}
    for abspath, relpath in infiles.items():
        afile = orm.SinglefileData(abspath, filename=relpath)
        aiida_files_by_relpath[relpath] = afile

    # I don't think we need these two walks here. They are here, because legacy applications required them
    rendered_wano = wmr.wano_walker()
    wmr.wano_walker_render_pass(
        rendered_wano,
        submitdir=None,
        flat_variable_list=None,
        input_var_db=None,
        output_var_db=None,
        runtime_variables=None,
    )
    with open(join(emdir(), "rendered_wano.yml"), "wt") as outfile:
        yaml.safe_dump(rendered_wano, outfile)
    rendered_wano = wmr.get_valuedict_with_aiida_types(
        aiida_files_by_relpath=aiida_files_by_relpath
    )
    import aiida

    aiida.load_profile()

    rendered_wano["static_extra_files"] = {}
    for dest, src in wmr.input_files:
        rendered_wano["static_extra_files"][
            WaNoCalcJob.dot_to_none(dest)
        ] = orm.SinglefileData(join(depdir(), src), filename=dest)
    rendered_wano["static_extra_files"]["rendered_wanoyml"] = orm.SinglefileData(
        join(depdir(), "rendered_wano.yml")
    )
    return rendered_wano


def get_parsed_dep_xml():
    wmr = WaNoModelRoot(wano_dir_root=Path(depdir()), model_only=True)
    with open(depxml(), "rt") as infile:
        xml = etree.parse(infile)
    wmr.parse_from_xml(xml)
    wmr = wano_without_view_constructor_helper(wmr)
    mol, spf = dep_inputs()
    wmr["TABS"]["Molecules"]["Molecules"][0]["Molecule"].set_data(mol)
    wmr["TABS"]["Molecules"]["Molecules"][0]["Forcefield"].set_data(spf)
    wmr.datachanged_force()
    wmr.datachanged_force()

    aiida_files_by_relpath = {}
    infiles = {mol: "molecule_0.pdb", spf: "molecule_0.spf"}
    for abspath, relpath in infiles.items():
        afile = orm.SinglefileData(abspath, filename=relpath)
        aiida_files_by_relpath[relpath] = afile

    # I don't think we need these two walks here. They are here, because legacy applications required them
    rendered_wano = wmr.wano_walker()
    wmr.wano_walker_render_pass(
        rendered_wano,
        submitdir=None,
        flat_variable_list=None,
        input_var_db=None,
        output_var_db=None,
        runtime_variables=None,
    )
    with open(join(depdir(), "rendered_wano.yml"), "wt") as outfile:
        yaml.safe_dump(rendered_wano, outfile)
    rendered_wano = wmr.get_valuedict_with_aiida_types(
        aiida_files_by_relpath=aiida_files_by_relpath
    )
    import aiida

    aiida.load_profile()

    rendered_wano["static_extra_files"] = {}
    for dest, src in wmr.input_files:
        rendered_wano["static_extra_files"][
            WaNoCalcJob.dot_to_none(dest)
        ] = orm.SinglefileData(join(depdir(), src), filename=dest)
    rendered_wano["static_extra_files"]["rendered_wanoyml"] = orm.SinglefileData(
        join(depdir(), "rendered_wano.yml")
    )
    return rendered_wano


def test_clean_aiida_dict():
    rendered_wano = get_parsed_dep_xml()
    outdict = clean_dict_for_aiida(rendered_wano)
    print(outdict)


def test_process(wano_code, generate_parser):
    """Test running a calculation
    note this does not test that the expected outputs are created of output parsing"""
    from aiida.plugins import CalculationFactory

    rendered_wano = get_parsed_dep_xml()
    outdict = clean_dict_for_aiida(rendered_wano)
    print(wano_code)

    # set up calculation
    inputs = {
        "code": wano_code,
        "metadata": {
            "options": {"max_wallclock_seconds": 30},
        },
    }
    inputs.update(outdict)

    result = run_get_node(CalculationFactory("Deposit3"), **inputs)
    myparser = Deposit3Parser(result.node)
    myparser.parse_from_node(result.node)
    # print("here")

    # Do: Submit Deposit
    # Write: Small python library to query status
    #

    # computed_diff = result['wano'].get_content()

    # assert 'content1' in computed_diff

    # assert 'content2' in computed_diff


def test_wano_namespace_conversion():
    wmr = WaNoCalcJob._parse_wano_xml(emxml())
    namespaces = WaNoCalcJob._wano_to_namespaces_and_vars(wmr)
    print(namespaces)

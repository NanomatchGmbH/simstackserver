""" Tests for calculations

"""
from os import path
from os.path import join
import sys

from aiida.orm import load_code
import aiida

from SimStackServer.SimAiiDA.AiiDAJob import AiiDAJob

ssspath = path.join(path.dirname(path.realpath(__file__)), "..", "..", "..")
print(ssspath)
sys.path.append(ssspath)
sys.path.append(join(ssspath, "external", "nestdictmod"))
sys.path.append(join(ssspath, "external", "boolexp"))

from aiida.engine import submit
from lxml import etree
from wano_calcjob.WaNoCalcJobBase import clean_dict_for_aiida

from SimStackServer.WaNo.WaNoFactory import wano_without_view_constructor_helper


def depdir():
    deposit_dir = "%s/../tests/inputs/wanos/Deposit" % path.dirname(
        path.realpath(__file__)
    )
    return deposit_dir


def dep_inputs():
    deposit_file_dir = "%s/../tests/input_files/" % path.dirname(
        path.realpath(__file__)
    )
    moleculepdb = join(deposit_file_dir, "molecule_0.pdb")
    moleculespf = join(deposit_file_dir, "molecule_0.spf")
    return moleculepdb, moleculespf


def depxml():
    depxml = path.join(depdir(), "Deposit3.xml")
    return depxml


from SimStackServer.WaNo.WaNoModels import WaNoModelRoot


def get_parsed_dep_xml():
    wmr = WaNoModelRoot(wano_dir_root=depdir(), model_only=True)
    with open(depxml(), "rt") as infile:
        xml = etree.parse(infile)
    wmr.parse_from_xml(xml)
    wmr = wano_without_view_constructor_helper(wmr)
    mol, spf = dep_inputs()
    wmr["TABS"]["Molecules"]["Molecules"][0]["Molecule"].set_data(mol)
    wmr["TABS"]["Molecules"]["Molecules"][0]["Forcefield"].set_data(spf)
    wmr.datachanged_force()
    wmr.datachanged_force()
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
    rendered_wano = wmr.get_valuedict_with_aiida_types()
    return rendered_wano


def test_submit():
    """Test running a calculation
    note this does not test that the expected outputs are created of output parsing"""
    from aiida.plugins import CalculationFactory

    aiida.load_profile()

    rendered_wano = get_parsed_dep_xml()
    outdict = clean_dict_for_aiida(rendered_wano)

    wano_code = load_code(label="Deposit3")
    # set up calculation
    inputs = {
        "code": wano_code,
        "metadata": {
            "options": {"max_wallclock_seconds": 30},
        },
    }
    # resources = {
    #         "num_machines": 1,
    #         "tot_num_mpiprocs": 1,
    #         "num_mpiprocs_per_machine": 1,
    #     }
    #     "max_wallclock_seconds": 10 * 60 * 60, # 10 hours
    #     "max_memory_kb": 2000000, # limiting the
    #     "withmpi": False
    # }
    inputs.update(outdict)
    # output = run_get_node(CalculationFactory('Deposit3'), **inputs).node
    output = submit(CalculationFactory("Deposit3"), **inputs)
    # pk = output.pk
    # print("submitted",pk)
    import time

    time.sleep(5)
    if output.is_excepted:
        print(output.is_excepted, output.exception)
    else:
        print("not excepted")
    print(output.is_failed, output.is_finished_ok)
    print(output.is_terminated, output.is_finished)
    print(output.is_terminated, output.is_finished)

    uuid = output.uuid
    myjon = AiiDAJob(uuid)
    print(myjon.status())
    myjon.listdir()

    myjon = AiiDAJob(uuid)
    outputs = myjon.get_outputs()
    breakpoint()

    myjon.listdir()
    for myoutput in outputs:
        mynode = outputs[myoutput]
        if mynode.class_node_type == "data.singlefile.SinglefileData.":
            print(mynode)
            dir(mynode)
        else:
            print("not staging", myoutput)
    assert output.is_finished, "not finished here"
    outfile = output.outputs["structurecml"]
    print(outfile.get_content(), "will be saved to", outfile.filename)
    # myjon.delete()
    print("Make this usable from python, not verdi")


if __name__ == "__main__":
    test_submit()

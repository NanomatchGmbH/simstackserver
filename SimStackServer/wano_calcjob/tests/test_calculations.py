""" Tests for calculations

"""
import os
from os import path


from aiida import orm
from wano_calcjob.calculations import WaNoCalcJob

from . import TEST_DIR

def depxml():
    deposit_dir = "%s/inputs/wanos/Deposit" % path.dirname(path.realpath(__file__))
    depxml = path.join(deposit_dir, "Deposit3.xml")
    return depxml

def test_process(wano_code):
    """Test running a calculation
    note this does not test that the expected outputs are created of output parsing"""
    from aiida.plugins import DataFactory, CalculationFactory
    from aiida.engine import run

    # Prepare input parameters
    DiffParameters = DataFactory('wano')
    parameters = DiffParameters({'ignore-case': True})

    from aiida.orm import SinglefileData
    file1 = SinglefileData(
        file=os.path.join(TEST_DIR, "input_files", 'file1.txt'))
    file2 = SinglefileData(
        file=os.path.join(TEST_DIR, "input_files", 'file2.txt'))

    # set up calculation
    inputs = {
        'code': wano_code,
        'parameters': parameters,
        'file1': file1,
        'file2': file2,
        'metadata': {
            'options': {
                'max_wallclock_seconds': 30
            },
        },
        'harbl' : { "my": { "garbl": {"mod" :{ "prop" :{ "humbo" : orm.Float(5.0)}} }}}
        #'harbl.my.garbl.0.prop.humbo'
        #'humbo': orm.Float(5.0)
    }

    result = run(CalculationFactory('wano'), **inputs)
    computed_diff = result['wano'].get_content()

    assert 'content1' in computed_diff
    assert 'content2' in computed_diff

def test_wano_namespace_conversion():
    wmr = WaNoCalcJob._parse_wano_xml(depxml())
    namespaces = WaNoCalcJob._wano_to_namespaces_and_vars(wmr)
    print(namespaces)
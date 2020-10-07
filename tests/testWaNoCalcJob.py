import os
import sys
import unittest


from os import path

from SimStackServer.WaNoCalcJob import WaNoCalcJob


from aiida import orm
from aiida.common import datastructures



def test_pw_default(fixture_database, fixture_computer_localhost, fixture_sandbox_folder, generate_calc_job,
                    generate_code_localhost, generate_structure, generate_kpoints_mesh, generate_upf_data):

    entry_point_name = 'arithmetic.add'

    parameters = {

    }

    inputs = {
        'code': generate_code_localhost(entry_point_name, fixture_computer_localhost),
        #'parameters': parameters,
        'metadata': {
            'options':
            {
                'resources':
                {
                    'num_machines': int(1)
                },
                'max_wallclock_seconds': int(500),
                'withmpi': False,
            }
        },
        'x':  orm.Float(5.0),
        'y':  orm.Float(7.0)
    }

    calc_info = generate_calc_job(fixture_sandbox_folder, entry_point_name, inputs)

    #cmdline_params = ['-in', 'aiida.in']
    #local_copy_list = [(upf.uuid, upf.filename, u'./pseudo/Si.upf')]
    retrieve_list = ['aiida.out']
    #retrieve_temporary_list = [['./out/aiida.save/K*[0-9]/eigenval*.xml', '.', 2]]

    # Check the attributes of the returned `CalcInfo`
    assert isinstance(calc_info, datastructures.CalcInfo)
    #assert sorted(calc_info.cmdline_params) == sorted(cmdline_params)
    #assert sorted(calc_info.local_copy_list) == sorted(local_copy_list)
    assert sorted(calc_info.retrieve_list) == sorted(retrieve_list)
    #assert sorted(calc_info.retrieve_temporary_list) == sorted(retrieve_temporary_list)
    assert sorted(calc_info.remote_symlink_list) == sorted([])

    #with fixture_sandbox_folder.open('aiida.in') as handle:
    #    input_written = handle.read()
    print("hello")
    # Checks on the files written to the sandbox folder as raw input
    #assert sorted(fixture_sandbox_folder.get_content_list()) == sorted(['aiida.in', 'pseudo', 'out'])

#!/usr/bin/env python3
import os
import pathlib
import sys
import uuid
from os.path import join

import yaml
from lxml import etree


if __name__ == '__main__':
    base_path = os.path.join((os.path.dirname(os.path.realpath(__file__))), os.pardir)
    sys.path.append(base_path)
    dir_path = join(base_path,"external","clusterjob")
    if not dir_path in sys.path:
        sys.path.append(dir_path)

    dir_path = join(base_path,"external","python-crontab")
    if not dir_path in sys.path:
        sys.path.append(dir_path)

    dir_path = join(base_path,"external","python-daemon")
    if not dir_path in sys.path:
        sys.path.append(dir_path)

    dir_path = join(base_path,"external","threadfarm")
    if not dir_path in sys.path:
        sys.path.append(dir_path)

    dir_path = join(base_path,"external","treewalker")
    if not dir_path in sys.path:
        sys.path.append(dir_path)

    dir_path = join(base_path,"external","boolexp")
    if not dir_path in sys.path:
        sys.path.append(dir_path)


from SimStackServer.WorkflowModel import WorkflowExecModule, Resources
from pathlib import Path
from SimStackServer.WaNo.MiscWaNoTypes import WaNoListEntry_from_folder_or_zip, WaNoListEntry, get_wano_xml_path
from SimStackServer.Util.FileUtilities import copytree_pathlib
from SimStackServer.WaNo.WaNoModels import WaNoModelRoot
from SimStackServer.WaNo.WaNoFactory import wano_without_view_constructor_helper
from SimStackServer.Util.ClientResourceModelToServerResourceModel import ClientResourceModelToServerResourceModel, \
    load_resource_list


def get_target_path():
    return Path("CI",str(uuid.uuid4()))

def get_resources(possible_resource_file_path: pathlib.Path):
    resources = Resources()
    if possible_resource_file_path.is_file():
        resources.from_json(possible_resource_file_path)
    return resources

def instantiate_wano(wano_dir_root, wanoxml):
    # MODELROOTDIRECT
    wmr = WaNoModelRoot(wano_dir_root=wano_dir_root, model_only=True)
    wmr.parse_from_xml(wanoxml)
    wmr = wano_without_view_constructor_helper(wmr)
    wmr.datachanged_force()
    wmr.datachanged_force()

    rendered_wano = wmr.wano_walker()
    rendered_wano = wmr.wano_walker_render_pass(rendered_wano, submitdir=None, flat_variable_list=None,
                                                input_var_db={},
                                                output_var_db={},
                                                runtime_variables={}
                                        )

    rendered_exec_command = wmr.render_exec_command(rendered_wano)
    res_path = wano_dir_root / "resources.yml"
    resources = get_resources(res_path)
    runtime_dir = os.path.abspath(wano_dir_root)
    wfem = WorkflowExecModule( uid = str(uuid.uuid4()),
                        given_name= "name",
                        queueing_system="OnlyScript",
                        runtime_directory=runtime_dir,
                        resources=resources
    )
    wfem.set_exec_command(rendered_exec_command)
    wfem.run_jobfile(wfem.queueing_system)
    with open(join(runtime_dir, "rendered_wano.yml"), 'wt') as outfile:
        yaml.safe_dump(rendered_wano, outfile)


def parse_xml(xmlpath: pathlib.Path):
    with xmlpath.open("rt") as infile:
        xml = etree.parse(infile).getroot()
        return xml

if __name__ == '__main__':
    rawpath = sys.argv[1]
    wle:WaNoListEntry = WaNoListEntry_from_folder_or_zip(rawpath)
    target_path = get_target_path()
    wano_path = target_path / "wano"
    print(f"Running in {target_path}.")
    os.makedirs(wano_path)
    copytree_pathlib(wle.folder, wano_path)
    print(f"WaNo in {wano_path}")
    ci_targets = wano_path / "ci_overlays"
    if not ci_targets.is_dir():
        print("Did not find any CI targets. Exiting.")
        sys.exit(0)
    for citest in ci_targets.iterdir():
        if citest.is_dir():
            ci_target_dir = target_path / citest.name
            os.makedirs(ci_target_dir)
            print(f"Running test for {citest} in {ci_target_dir}")
            copytree_pathlib(wano_path, ci_target_dir)
            copytree_pathlib(citest, ci_target_dir)
            ci_wle :WaNoListEntry = WaNoListEntry_from_folder_or_zip(str(ci_target_dir))
            xmlpath = get_wano_xml_path(ci_wle.folder, wano_name_override=wle.name)
            xml = parse_xml(xmlpath)
            mywano = instantiate_wano(ci_wle.folder, xml)

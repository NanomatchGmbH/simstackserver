#!/usr/bin/env python3

import os
import sys
import time
from os import path
from os.path import join
from pathlib import Path

if __name__ == '__main__':
    base_path = join(os.path.dirname(os.path.realpath(__file__)),"..")
    if not base_path in sys.path:
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

from SimStackServer.WorkflowModel import Workflow


def wf_submit(folder: Path, wf_xml_loc: Path) -> None:
    """
    Local Jobserver used for testing. Will basically iterate only a single XML
    file until it finishes or aborts.

    :param folder:
        The folder the workflow is in

    :param wf_xml_loc:
        The path of the XML file

    :return:
        None
    """
    wf = Workflow.new_instance_from_xml(wf_xml_loc)
    wf.set_storage(Path(folder))
    maxcounter = 20
    for counter in range(0, maxcounter + 1):
        finished = wf.jobloop()
        if finished:
            break
        time.sleep(10.0)
        print(f"jobloop number {counter}")
    print("Finished workflow. Exiting.")

if __name__ == '__main__':
    argv = sys.argv
    if len(argv) < 2:
        print("Please call this script using TestRemoteWFSubmit.py your_wf_xml_file.xml")
    wf_xml = Path(sys.argv[1])
    wf_dir = wf_xml.parent

    print(f"Starting {wf_xml} in {wf_dir}.")
    wf_submit(wf_dir, wf_xml)
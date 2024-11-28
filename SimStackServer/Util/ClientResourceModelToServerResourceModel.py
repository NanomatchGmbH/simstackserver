from enum import IntEnum
import pathlib

import yaml


class ResourceROWTYPE(IntEnum):
    ppn = 0
    numnodes = 1
    mem = 2
    time = 3
    queue = 4
    custom_requests = 5


def get_default_resource_list():
    return [
        [False, "CPUs per Node", 1],
        [False, "Number of Nodes", 1],
        [False, "Memory [MB]", 1024],
        [False, "Time [Wall]", 86400],
        [False, "Queue", "default"],
        [False, "Custom Requests", ""],
    ]


def load_resource_list(filename: pathlib.Path):
    default_list = get_default_resource_list()

    with filename.open("rt") as infile:
        updatelist = yaml.safe_load(infile)

    updatedict = {b[1]: b for b in updatelist}
    for entry in default_list:
        if entry[1] in updatedict:
            for num in [0, 2]:
                entry[num] = updatedict[entry[1]][num]
    return default_list


def ClientResourceModelToServerResourceModel(client_list: list):
    from SimStackServer.WorkflowModel import Resources

    ppn = None
    if client_list[ResourceROWTYPE.ppn][0] is True:
        ppn = client_list[ResourceROWTYPE.ppn][2]

    numnodes = None
    if client_list[ResourceROWTYPE.numnodes][0] is True:
        numnodes = client_list[ResourceROWTYPE.numnodes][2]

    mem = None
    if client_list[ResourceROWTYPE.mem][0] is True:
        mem = int(float(client_list[ResourceROWTYPE.mem][2]))

    time = None
    if client_list[ResourceROWTYPE.time][0] is True:
        time = client_list[ResourceROWTYPE.time][2]

    queue = None
    if client_list[ResourceROWTYPE.queue][0] is True:
        queue = client_list[ResourceROWTYPE.queue][2]
    else:
        queue = "${QUEUE_NAME}"

    custom_requests = None
    if client_list[ResourceROWTYPE.custom_requests][0] is True:
        custom_requests = client_list[ResourceROWTYPE.custom_requests][2]

    return Resources(
        cpus_per_node=ppn,
        nodes=numnodes,
        memory=mem,
        walltime=time,
        queue=queue,
        custom_requests=custom_requests,
    )

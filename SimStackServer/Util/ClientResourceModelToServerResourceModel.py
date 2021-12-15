from enum import IntEnum


class ResourceROWTYPE(IntEnum):
    ppn = 0
    numnodes = 1
    mem = 2
    time = 3
    queue = 4
    custom_requests = 5

def ClientResourceModelToServerResourceModel(client_list: list):
    from SimStackServer.WorkflowModel import Resources

    ppn = None
    if client_list[ResourceROWTYPE.ppn][0] == True:
        ppn = client_list[ResourceROWTYPE.ppn][2]

    numnodes = None
    if client_list[ResourceROWTYPE.numnodes][0] == True:
        numnodes = client_list[ResourceROWTYPE.numnodes][2]

    mem = None
    if client_list[ResourceROWTYPE.mem][0] == True:
        mem = int(float(client_list[ResourceROWTYPE.mem][2]))

    time = None
    if client_list[ResourceROWTYPE.time][0] == True:
        time = client_list[ResourceROWTYPE.time][2]

    queue = None
    if client_list[ResourceROWTYPE.queue][0] == True:
        queue = client_list[ResourceROWTYPE.queue][2]
    else:
        queue = "${QUEUE_NAME}"

    custom_requests = None
    if client_list[ResourceROWTYPE.custom_requests][0] == True:
        custom_requests = client_list[ResourceROWTYPE.custom_requests][2]

    return Resources(
        cpus_per_node=ppn, nodes=numnodes,
        memory=mem, walltime=time,
        queue=queue, custom_requests=custom_requests
    )


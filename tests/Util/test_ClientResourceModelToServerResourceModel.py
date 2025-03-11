from unittest.mock import patch

import yaml

from SimStackServer.Util.ClientResourceModelToServerResourceModel import ResourceROWTYPE, get_default_resource_list, load_resource_list, ClientResourceModelToServerResourceModel

def test_ResourceROWTYPE():
    rrt = ResourceROWTYPE(0)
    assert rrt.ppn == 0
    rrt = ResourceROWTYPE(4)
    assert rrt.queue == 4

def test_get_default_resource_list():
    target_list = [
        [False, "CPUs per Node", 1],
        [False, "Number of Nodes", 1],
        [False, "Memory [MB]", 1024],
        [False, "Time [Wall]", 86400],
        [False, "Queue", "default"],
        [False, "Custom Requests", ""],
    ]
    mylist = get_default_resource_list()
    for t in target_list:
        assert t in mylist

def test_load_resource_list(tmpfile):
    update_list = [
        [False, "CPUs per Node", 2],
        [False, "Queue", "night"],
    ]
    with tmpfile.open("w") as outfile:
        yaml.safe_dump(update_list, outfile)

    returned_list = load_resource_list(tmpfile)
    assert returned_list[ResourceROWTYPE.ppn][2] == 2
    assert returned_list[ResourceROWTYPE.queue][2] == "night"

def test_ClientResourceModelToServerResourceModel():
    my_client_list = get_default_resource_list()
    for i in range(6):
        my_client_list[i][0] = True
    my_client_list[ResourceROWTYPE.ppn][2] = 16
    my_client_list[ResourceROWTYPE.queue][2] = "somequeue"
    my_client_list[ResourceROWTYPE.mem][2] = 1234
    my_client_list[ResourceROWTYPE.time][2] = 12345
    my_client_list[ResourceROWTYPE.custom_requests][2] = "more_colakracher"

    def mock_resources(cpus_per_node, nodes, memory, walltime, queue, custom_requests):
        return cpus_per_node, nodes, memory, walltime, queue, custom_requests

    with patch("SimStackServer.WorkflowModel.Resources", side_effect=mock_resources):
        returned_args = ClientResourceModelToServerResourceModel(my_client_list)
        assert returned_args == (16, 1, 1234, 12345, 'somequeue', 'more_colakracher')

        my_client_list[ResourceROWTYPE.queue][0] = False
        returned_args = ClientResourceModelToServerResourceModel(my_client_list)
        assert returned_args == (16, 1, 1234, 12345, '${QUEUE_NAME}', 'more_colakracher')
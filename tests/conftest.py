import pytest
import tempfile
import os
from SimStackServer.WaNo.WaNoModels import (
    WaNoModelRoot,
)

from SimStackServer.WorkflowModel import (
    Resources,
    WorkflowExecModule,
)


@pytest.fixture
def tmpdir() -> tempfile.TemporaryDirectory:
    with tempfile.TemporaryDirectory() as mydir:
        yield mydir


@pytest.fixture
def tmpfile(tmp_path):
    tmpfile = tmp_path / "tmp_file.dat"

    # Just touching the file ensures it exists; or you can open/write to it.
    tmpfile.touch()

    yield tmpfile


@pytest.fixture
def tmpfileWaNoXml(tmp_path):
    """Create a file named 'WaNo.xml' in a unique temp dir."""
    path = tmp_path / "WaNo"
    path.mkdir()

    xmlfile = path / "WaNo.xml"

    # Just touching the file ensures it exists; or you can open/write to it.
    xmlfile.touch()

    # If you need an open file handle:
    # with path.open("w") as f:
    #     yield f

    # If you only need the path:
    yield xmlfile

@pytest.fixture
def tmpfile(tmp_path):
    """Create a file named 'WaNo.xml' in a unique temp dir."""
    newfile = tmp_path / "testfile.dat"

    newfile.touch()

    # If you need an open file handle:
    # with path.open("w") as f:
    #     yield f

    # If you only need the path:
    yield newfile


@pytest.fixture
def tmpWaNoRoot(tmpfileWaNoXml, tmpdir):
    xml_root_string = """
        <WaNoTemplate>
            <WaNoRoot name="DummyRoot">
                <WaNoInt name="dummy_int">0</WaNoInt>
            </WaNoRoot>
            <WaNoExecCommand>echo Hello</WaNoExecCommand>
            <WaNoOutputFiles>
                <WaNoOutputFile>output_config.ini</WaNoOutputFile>
                <WaNoOutputFile>output_dict.yml</WaNoOutputFile>
            </WaNoOutputFiles>
            <WaNoInputFiles>
               <WaNoInputFile logical_filename="deposit_init.sh">deposit_init.sh</WaNoInputFile>
               <WaNoInputFile logical_filename="report_template.body">report_template.body</WaNoInputFile>
            </WaNoInputFiles>
        </WaNoTemplate>
    """
    # Write the XML contents to the file
    with tmpfileWaNoXml.open("w") as f:
        f.write(xml_root_string)

    # Initialize WaNoModelRoot
    # wano_dir_root is the directory containing WaNo.xml
    current_directory = tmpfileWaNoXml.parent
    wm = WaNoModelRoot(model_only=True, wano_dir_root=current_directory)

    # Yield the fully-initialized instance for use in tests
    yield wm


@pytest.fixture
def workflow_exec_module_fixture(tmpdir):
    """
    Returns a WorkflowExecModule instance with minimal (but valid) defaults for pytest.
    """
    # Create a minimal Resources object (adjust fields as needed in your code).
    resources = Resources(
        # You may need to fill other fields depending on how Resources is defined
        # or if it inherits from XMLYMLInstantiationBase with required fields.
        resource_name=None,
        queueing_system="Internal",  # or "unset" or "slurm", etc.
        cpus_per_node=1,
        nodes=1,
        memory="1GB",
        custom_requests="",
        reuse_results=False,
    )

    # Construct a minimal WorkflowElementList for inputs/outputs:
    # inputs_list = workflow_element_factory("WorkflowElementList")
    # outputs_list = workflow_element_factory("WorkflowElementList")

    if "CONDA_PREFIX" not in os.environ:
        os.environ["CONDA_PREFIX"] = "/opt/conda/envs/myenv"

    # Instantiate the WorkflowExecModule with some defaults
    wfem = WorkflowExecModule(
        uid="0c3f3863-c696-42a4-8ff5-4d5e3222d39a",
        given_name="TestWFEM",
        path="test_path",
        wano_xml="test_wano.xml",
        outputpath="testdir",  # or "unset"
        original_result_directory="",
        # inputs=inputs_list,
        # outputs=outputs_list,
        exec_command="echo 'Hello, WorkflowExecModule!'",
        resources=resources,
        runtime_directory="unstarted",
        jobid="unstarted",
        external_runtime_directory="",
    )

    return wfem

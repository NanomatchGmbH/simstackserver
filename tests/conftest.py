import pytest
import tempfile

from SimStackServer.WaNo.WaNoModels import (
    WaNoModelRoot,
)


@pytest.fixture
def tmpdir() -> tempfile.TemporaryDirectory:
    with tempfile.TemporaryDirectory() as mydir:
        yield mydir


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

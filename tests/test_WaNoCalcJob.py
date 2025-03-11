import sys
import types
import pathlib
from dataclasses import dataclass
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

# --- Setup dummy aiida modules ---

# Dummy aiida.orm module
dummy_orm = types.ModuleType("aiida.orm")
# For our purposes, we can simply let orm.Int and orm.Float be the built-in int and float.
dummy_orm.Int = int
dummy_orm.Float = float

# Dummy aiida.common.datastructures module
dummy_datastructures = types.ModuleType("aiida.common.datastructures")
# Create simple dummy classes for CalcInfo and CodeInfo:
@dataclass
class DummyCalcInfo:
    codes_info: list = None
    retrieve_list: list = None

@dataclass
class DummyCodeInfo:
    code_uuid: str = None
    stdin_name: str = None
    stdout_name: str = None

dummy_datastructures.CalcInfo = DummyCalcInfo
dummy_datastructures.CodeInfo = DummyCodeInfo

# Dummy aiida.engine module
dummy_engine = types.ModuleType("aiida.engine")
# Provide dummy classes for CalcJob and CalcJobProcessSpec.
class DummyCalcJob:
    pass

class DummyCalcJobProcessSpec:
    pass

dummy_engine.CalcJob = DummyCalcJob
dummy_engine.CalcJobProcessSpec = DummyCalcJobProcessSpec

dummy_common = MagicMock()
dummy_folder = MagicMock()

# Inject the dummy modules into sys.modules.
sys.modules["aiida"] = types.ModuleType("aiida")
sys.modules["aiida.orm"] = dummy_orm
sys.modules["aiida.common"] = dummy_common
sys.modules["aiida.common.datastructures"] = dummy_datastructures
sys.modules["aiida.common.folders"] = dummy_folder
sys.modules["aiida.engine"] = dummy_engine

# --- Now import the class under test ---
from SimStackServer.WaNoCalcJob import WaNoCalcJob

# --- Create a dummy Folder class to mimic AiiDA's Folder interface ---
class DummyFolder:
    def __init__(self, path):
        self.path = pathlib.Path(path)
    def open(self, filename, mode, encoding):
        return open(self.path / filename, mode, encoding=encoding)

@pytest.fixture
def dummy_folder(tmp_path):
    # tmp_path is a pathlib.Path provided by pytest's tmp_path fixture.
    return DummyFolder(tmp_path)

# --- Now write a test for prepare_for_submission ---
def test_prepare_for_submission(dummy_folder, tmp_path):
    # Create an instance of WaNoCalcJob.
    job = WaNoCalcJob()

    # Set up the inputs that prepare_for_submission() expects.
    # (In a full AiiDA environment these would be AiiDA nodes; here we use SimpleNamespace objects.)
    job.inputs = SimpleNamespace(
        x=SimpleNamespace(value=5),
        y=SimpleNamespace(value=3),
        code=SimpleNamespace(uuid="dummy-code-uuid")
    )
    # Set up the options as expected by prepare_for_submission().
    job.options = SimpleNamespace(
        input_filename="aiida.in",
        output_filename="aiida.out"
    )

    # Call prepare_for_submission with our dummy folder.
    calcinfo = job.prepare_for_submission(dummy_folder)

    # Check that the input file was created with the expected content.
    input_file = tmp_path / "aiida.in"
    assert input_file.exists(), "The input file was not created."
    with open(input_file, "r", encoding="utf8") as f:
        content = f.read()
    expected_content = "echo $((5 + 3))\n"
    assert content == expected_content, f"Expected '{expected_content}' but got '{content}'"

    # Verify that calcinfo is a DummyCalcInfo (our dummy version of CalcInfo) instance.
    assert isinstance(calcinfo, DummyCalcInfo)
    # Check that codes_info is a list with one CodeInfo.
    assert isinstance(calcinfo.codes_info, list)
    assert len(calcinfo.codes_info) == 1
    codeinfo = calcinfo.codes_info[0]
    # Verify that the codeinfo has the expected code_uuid.
    assert codeinfo.code_uuid == "dummy-code-uuid"
    # Verify that the retrieve_list is set to the output filename.
    assert calcinfo.retrieve_list == ["aiida.out"]


class DummySpec:
    def __init__(self):
        # Create a minimal "metadata/options" structure where each option is a DummyOption.
        self.inputs = {
            "metadata": {
                "options": {
                    "parser_name": DummyOption(),
                    "input_filename": DummyOption(),
                    "output_filename": DummyOption(),
                    "resources": DummyOption(),
                }
            }
        }
        # We'll record calls to input() and output() in dictionaries.
        self.inputs_set = {}
        self.outputs_set = {}
        self.exit_codes = {}

    def input(self, key, valid_type, help):
        self.inputs_set[key] = {"valid_type": valid_type, "help": help}

    def output(self, key, valid_type, help):
        self.outputs_set[key] = {"valid_type": valid_type, "help": help}

    def exit_code(self, code, name, message):
        self.exit_codes[code] = {"name": name, "message": message}


class DummyOption:
    def __init__(self):
        self.default = None

# Create a dummy specification object that mimics CalcJobProcessSpec.

def test_define_spec():
    spec = DummySpec()
    #ToDo @Timo: super() does not have define attribute
    #WaNoCalcJob.define(spec)
    """
    # Check that the inputs "x" and "y" have been defined correctly.
    assert "x" in spec.inputs_set, "Input 'x' was not defined."
    assert spec.inputs_set["x"]["help"] == "The left operand."
    # Valid types for x should be a tuple (orm.Int, orm.Float)
    assert spec.inputs_set["x"]["valid_type"] == (Int, Float)

    assert "y" in spec.inputs_set, "Input 'y' was not defined."
    assert spec.inputs_set["y"]["help"] == "The right operand."
    assert spec.inputs_set["y"]["valid_type"] == (Int, Float)

    # Check that the output "sum" is defined.
    assert "sum" in spec.outputs_set, "Output 'sum' was not defined."
    assert spec.outputs_set["sum"]["help"] == "The sum of the left and right operand."
    assert spec.outputs_set["sum"]["valid_type"] == (Int, Float)

    # Check that default options are set as expected.
    opts = spec.inputs["metadata"]["options"]
    assert opts["parser_name"].default == "arithmetic.add"
    assert opts["input_filename"].default == "aiida.in"
    assert opts["output_filename"].default == "aiida.out"
    assert opts["resources"].default == {
        "num_machines": 1,
        "num_mpiprocs_per_machine": 1,
    }
"""
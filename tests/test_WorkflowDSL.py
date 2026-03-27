"""Tests for the WorkflowDSL composition API."""

import os
import pathlib
import tempfile
from pathlib import Path
from unittest import mock

import pytest
from lxml import etree

# EmployeeRecord lives inside an `inputs/` subdirectory (nested layout).
# Used for all integration tests since it has no WaNoFile parameters.
WANO_DIR = (
    Path(__file__).parent
    / "input_dirs/Complete_Workflow/workflow_data/EmployeeRecord/inputs"
)

# Alias for the nested-layout test
WANO_DIR_NESTED = WANO_DIR


@pytest.fixture(autouse=True)
def conda_prefix_tmpdir():
    with tempfile.TemporaryDirectory() as tmpdirname:
        prefix = pathlib.Path(tmpdirname) / "envs" / "simstack_server_v6"
        with mock.patch.dict(os.environ, {"CONDA_PREFIX": str(prefix)}):
            os.makedirs(os.path.join(tmpdirname, "envs"), exist_ok=True)
            yield tmpdirname


# ---------------------------------------------------------------------------
# Composition operator tests (pure Python, no WaNo loading)
# ---------------------------------------------------------------------------


def test_sequential_chain_repr():
    from SimStackServer.WorkflowDSL import Step

    a = Step.__new__(Step)
    a.node_name = "A"
    a.wano_dir = Path(".")
    a.params = {}

    b = Step.__new__(Step)
    b.node_name = "B"
    b.wano_dir = Path(".")
    b.params = {}

    chain = a >> b
    assert repr(chain) == "Step('A') >> Step('B')"


def test_parallel_repr():
    from SimStackServer.WorkflowDSL import Step

    a = Step.__new__(Step)
    a.node_name = "A"
    a.wano_dir = Path(".")
    a.params = {}

    b = Step.__new__(Step)
    b.node_name = "B"
    b.wano_dir = Path(".")
    b.params = {}

    para = a & b
    assert repr(para) == "(Step('A') & Step('B'))"


def test_mixed_composition_repr():
    from SimStackServer.WorkflowDSL import Step

    def _stub(name):
        s = Step.__new__(Step)
        s.node_name = name
        s.wano_dir = Path(".")
        s.params = {}
        return s

    a, b, c = _stub("A"), _stub("B"), _stub("C")
    comp = (a & b) >> c
    assert repr(comp) == "(Step('A') & Step('B')) >> Step('C')"


def test_foreach_creates_parallel():
    from SimStackServer.WorkflowDSL import Step, Parallel, foreach

    result = foreach(
        ["X", "Y"],
        lambda n: Step.__new__(Step),
    )
    assert isinstance(result, Parallel)
    assert len(result._branches) == 2


# ---------------------------------------------------------------------------
# _decompose tests (DAG wiring logic)
# ---------------------------------------------------------------------------


def _stub_step(name: str):
    from SimStackServer.WorkflowDSL import Step

    s = Step.__new__(Step)
    s.node_name = name
    s.wano_dir = Path(".")
    s.params = {}
    return s


def test_decompose_single_step():
    from SimStackServer.WorkflowDSL import _decompose

    s = _stub_step("A")
    entries, exits, specs = _decompose(s, ["0"])
    assert entries == ["A"]
    assert exits == ["A"]
    assert len(specs) == 1
    node_name, preds, step = specs[0]
    assert node_name == "A"
    assert preds == ["0"]


def test_decompose_chain():
    from SimStackServer.WorkflowDSL import _decompose

    a, b, c = _stub_step("A"), _stub_step("B"), _stub_step("C")
    chain = a >> b >> c
    entries, exits, specs = _decompose(chain, ["0"])
    assert entries == ["A"]
    assert exits == ["C"]

    preds_by_name = {n: p for n, p, _ in specs}
    assert preds_by_name["A"] == ["0"]
    assert preds_by_name["B"] == ["A"]
    assert preds_by_name["C"] == ["B"]


def test_decompose_parallel():
    from SimStackServer.WorkflowDSL import _decompose

    a, b = _stub_step("A"), _stub_step("B")
    para = a & b
    entries, exits, specs = _decompose(para, ["0"])
    assert set(entries) == {"A", "B"}
    assert set(exits) == {"A", "B"}
    preds_by_name = {n: p for n, p, _ in specs}
    assert preds_by_name["A"] == ["0"]
    assert preds_by_name["B"] == ["0"]


def test_decompose_fan_out_join():
    """(A & B) >> C: A and B both depend on 0, C depends on both A and B."""
    from SimStackServer.WorkflowDSL import _decompose

    a, b, c = _stub_step("A"), _stub_step("B"), _stub_step("C")
    comp = (a & b) >> c
    entries, exits, specs = _decompose(comp, ["0"])
    assert entries == ["A", "B"]
    assert exits == ["C"]
    preds_by_name = {n: p for n, p, _ in specs}
    assert preds_by_name["A"] == ["0"]
    assert preds_by_name["B"] == ["0"]
    assert sorted(preds_by_name["C"]) == ["A", "B"]


# ---------------------------------------------------------------------------
# Integration test: build a real two-step workflow
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not WANO_DIR.exists(), reason="WaNo fixture not found")
def test_build_sequential_workflow_xml():
    """Build a 2-step sequential workflow and verify the XML structure."""
    from SimStackServer.WorkflowDSL import Step

    alice = Step(WANO_DIR, node_name="Alice", name="Alice", Job="Developer")
    bob = Step(WANO_DIR, node_name="Bob", name="Bob", Job="Developer")

    wf = (alice >> bob).build("test_seq_wf")
    xml_bytes = wf.to_xml()

    root = etree.fromstring(xml_bytes)
    assert root.tag == "Workflow"

    elements = root.find("elements")
    assert elements is not None
    # given_name is the WaNo type; path is the node_name we assigned
    paths = [el.get("path") for el in elements]
    assert "Alice" in paths
    assert "Bob" in paths

    # Graph must have at least 2 edges: 0->Alice, Alice->Bob
    graph = root.find("graph")
    assert graph is not None
    NS = "http://graphml.graphdrawing.org/xmlns"
    edges = graph.findall(f".//{{{NS}}}edge")
    assert len(edges) >= 2


@pytest.mark.skipif(not WANO_DIR.exists(), reason="WaNo fixture not found")
def test_build_parallel_workflow_xml():
    """Build a fan-out/join workflow and verify all graph edges exist."""
    from SimStackServer.WorkflowDSL import Step

    a = Step(WANO_DIR, node_name="ParA", name="Alice", Job="Developer")
    b = Step(WANO_DIR, node_name="ParB", name="Bob", Job="Developer")
    c = Step(WANO_DIR, node_name="Join", name="Charlie", Job="Developer")

    wf = ((a & b) >> c).build("test_par_wf")
    xml_bytes = wf.to_xml()

    root = etree.fromstring(xml_bytes)
    graph = root.find("graph")
    assert graph is not None
    NS = "http://graphml.graphdrawing.org/xmlns"
    # 0->A, 0->B, A->C, B->C = 4 edges minimum
    edges = graph.findall(f".//{{{NS}}}edge")
    assert len(edges) >= 4


@pytest.mark.skipif(not WANO_DIR_NESTED.exists(), reason="WaNo fixture not found")
def test_build_with_nested_inputs_dir():
    """Nested WaNo layout (wano_name/inputs/wano_name.xml) is also handled."""
    from SimStackServer.WorkflowDSL import Step

    s = Step(WANO_DIR_NESTED, node_name="NestStep", name="Nested")
    wf = s.build("test_nested_wf")
    xml_bytes = wf.to_xml()
    root = etree.fromstring(xml_bytes)
    assert root.tag == "Workflow"


# ---------------------------------------------------------------------------
# Integration test: Deposit WaNo with nested parameter overrides
# ---------------------------------------------------------------------------

DEPOSIT_WANO_DIR = Path(__file__).parent / "inputs/wanos/Deposit"


@pytest.mark.skipif(not DEPOSIT_WANO_DIR.exists(), reason="Deposit WaNo not found")
def test_build_deposit_workflow_with_restart():
    """Two Deposit steps: the second restarts from the first's output.

    Demonstrates nested dict params, conditional visibility (Restartfile
    becomes visible when 'Restart from existing morphology' is True), and
    variable references between steps.
    """
    from SimStackServer.WorkflowDSL import Step

    initial = Step(
        DEPOSIT_WANO_DIR,
        node_name="InitialDeposit",
        TABS={
            "Simulation Parameters": {
                "Simulation Box": {
                    "Lx": 80.0,
                    "Ly": 80.0,
                    "Lz": 80.0,
                    "PBC": {"enabled": True, "Cutoff": 40.0},
                },
                "Simulation Parameters": {"Number of Molecules": 50},
            },
            "Postprocessing": {"Extend morphology (x,y)": False},
        },
    )
    continued = Step(
        DEPOSIT_WANO_DIR,
        node_name="ContinuedDeposit",
        TABS={
            "Simulation Parameters": {
                "Simulation Box": {
                    "Lx": 80.0,
                    "Ly": 80.0,
                    "Lz": 80.0,
                    "PBC": {"enabled": True, "Cutoff": 40.0},
                },
                "Simulation Parameters": {"Number of Molecules": 50},
            },
            "Molecules": {
                "Restart from existing morphology": True,
                "Restartfile": "global://${InitialDeposit/restartfile.zip}",
            },
        },
    )

    wf = (initial >> continued).build("test_deposit_wf")
    xml_bytes = wf.to_xml()

    root = etree.fromstring(xml_bytes)
    assert root.tag == "Workflow"

    # Both steps present
    elements = root.find("elements")
    assert elements is not None
    paths = [el.get("path") for el in elements]
    assert "InitialDeposit" in paths
    assert "ContinuedDeposit" in paths

    # Graph: 0->InitialDeposit->ContinuedDeposit = 2 edges
    NS = "http://graphml.graphdrawing.org/xmlns"
    graph = root.find("graph")
    assert graph is not None
    edges = graph.findall(f".//{{{NS}}}edge")
    assert len(edges) == 2

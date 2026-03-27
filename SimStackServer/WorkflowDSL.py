"""
SimStack Workflow DSL
====================

A Python-native composition API for building SimStack workflows.
Instead of manually constructing XML or managing UUIDs, use operator overloading:

    from SimStackServer.WorkflowDSL import Step

    alice = Step(WANO_DIR, node_name="Alice", name="Alice", job="Developer")
    bob   = Step(WANO_DIR, node_name="Bob",   name="Bob",   job="Manager")

    # Sequential (alice runs first, then bob)
    pipeline = alice >> bob

    # Parallel (alice and bob run simultaneously, then charlie)
    pipeline = (alice & bob) >> charlie

    # Build into an internal Workflow object
    wf = pipeline.build("my_workflow")

    # Serialize to XML for the REST API
    xml_bytes = wf.to_xml()

    # Or upload and submit in one call
    wf.submit("http://localhost:8080")

Variable references
-------------------
Use ``${NODE_NAME/output_key}``-style strings in parameter values to wire
outputs of one step into inputs of a later step (resolved at runtime by the
server's variable substitution engine):

    alice = Step(WANO_DIR, node_name="Alice", name="Alice")
    bob   = Step(WANO_DIR, node_name="Bob",   name="${Alice/name}")
    pipeline = alice >> bob
"""

from __future__ import annotations

import datetime
import tempfile
from pathlib import Path
from typing import Union

from lxml import etree

from SimStackServer.MessageTypes import JobStatus
from SimStackServer.WaNo.WaNoModels import WaNoModelRoot
from SimStackServer.WorkflowModel import (
    DirectedGraph,
    Workflow,
    WorkflowElementList,
    WorkflowExecModule,
)


# ---------------------------------------------------------------------------
# Counter for auto-generating unique node names
# ---------------------------------------------------------------------------

_name_counter: dict[str, int] = {}


def _unique_name(base: str) -> str:
    idx = _name_counter.get(base, 0)
    _name_counter[base] = idx + 1
    return base if idx == 0 else f"{base}_{idx}"


# ---------------------------------------------------------------------------
# Public composition types
# ---------------------------------------------------------------------------


class Step:
    """A single WaNo step with bound parameters.

    Parameters
    ----------
    wano_dir:
        Path to the WaNo directory (must contain a ``<WaNoName>.xml`` file).
    node_name:
        Label for this step in the workflow DAG.  Must be unique within a
        workflow.  Defaults to the WaNo directory name.
    **params:
        WaNo parameter overrides.  Keys match WaNo XML element names;
        values are passed to ``apply_delta``.
    """

    def __init__(
        self,
        wano_dir: str | Path,
        node_name: str | None = None,
        **params,
    ) -> None:
        self.wano_dir = Path(wano_dir)
        raw_name = node_name or self.wano_dir.name
        self.node_name = _unique_name(raw_name)
        self.params = params

    def __rshift__(self, other: _Composable) -> Chain:
        """``self >> other`` — run *self* before *other*."""
        return Chain([self]) >> other

    def __and__(self, other: _Composable) -> Parallel:
        """``self & other`` — run *self* and *other* concurrently."""
        return Parallel([self]) & other

    def build(
        self,
        name: str,
        storage: str | None = None,
        queueing_system: str = "Internal",
    ) -> BuiltWorkflow:
        """Shortcut: build a single-step workflow."""
        return Chain([self]).build(name, storage, queueing_system)

    def __repr__(self) -> str:
        return f"Step({self.node_name!r})"


class Chain:
    """Sequential composition — steps run one after another."""

    def __init__(self, items: list[_Composable]) -> None:
        self._items: list[_Composable] = list(items)

    def __rshift__(self, other: _Composable) -> Chain:
        """Append *other* after this chain."""
        tail = other._items if isinstance(other, Chain) else [other]
        return Chain(self._items + tail)

    def __and__(self, other: _Composable) -> Parallel:
        """Turn this chain into a parallel branch alongside *other*."""
        return Parallel([self]) & other

    def build(
        self,
        name: str,
        storage: str | None = None,
        queueing_system: str = "Internal",
    ) -> BuiltWorkflow:
        return _build(self, name, storage, queueing_system)

    def __repr__(self) -> str:
        return " >> ".join(repr(i) for i in self._items)


class Parallel:
    """Parallel composition — all branches run concurrently."""

    def __init__(self, branches: list[_Composable]) -> None:
        self._branches: list[_Composable] = list(branches)

    def __and__(self, other: _Composable) -> Parallel:
        """Add another branch to this parallel group."""
        extra = other._branches if isinstance(other, Parallel) else [other]
        return Parallel(self._branches + extra)

    def __rshift__(self, other: _Composable) -> Chain:
        """Run *other* after all branches in this parallel group finish."""
        return Chain([self]) >> other

    def build(
        self,
        name: str,
        storage: str | None = None,
        queueing_system: str = "Internal",
    ) -> BuiltWorkflow:
        return _build(self, name, storage, queueing_system)

    def __repr__(self) -> str:
        return "(" + " & ".join(repr(b) for b in self._branches) + ")"


_Composable = Union[Step, Chain, Parallel]


# ---------------------------------------------------------------------------
# foreach helper
# ---------------------------------------------------------------------------


def foreach(
    items: list,
    factory,
) -> Parallel:
    """Run a step for each item in *items* concurrently.

    *factory* receives each element and must return a ``Step``
    (or a ``Chain`` / ``Parallel`` sub-workflow).

    Example::

        names = ["Alice", "Bob", "Charlie"]
        fan_out = foreach(names, lambda n: Step(WANO_DIR, node_name=n, name=n))
        pipeline = fan_out >> postprocess
    """
    branches = [factory(item) for item in items]
    return Parallel(branches)


# ---------------------------------------------------------------------------
# BuiltWorkflow
# ---------------------------------------------------------------------------


class BuiltWorkflow:
    """A fully constructed workflow ready for submission."""

    def __init__(
        self,
        workflow: Workflow,
        staging_dir: Path,
        storage: str,
        server_basepath: str = "simstack_workspace",
    ) -> None:
        self._workflow = workflow
        self.staging_dir = staging_dir
        self.storage = storage
        self._server_basepath = server_basepath
        prefix = server_basepath.rstrip("/") + "/"
        self.upload_base = (
            storage[len(prefix) :] if storage.startswith(prefix) else storage
        )

    def to_xml(self) -> bytes:
        """Return the ``rendered_workflow.xml`` content as UTF-8 bytes."""
        root = etree.Element("Workflow")
        self._workflow.to_xml(root)
        return etree.tostring(root, pretty_print=True, encoding="unicode").encode()

    def submit(
        self,
        server_url: str,
        *,
        username: str | None = None,
        password: str | None = None,
    ) -> str:
        """Upload staged files and submit the workflow to a SimStack server.

        Returns the server path to the uploaded ``rendered_workflow.xml``.
        """
        import requests
        from requests.auth import HTTPBasicAuth

        auth = HTTPBasicAuth(username, password) if (username and password) else None  # type: ignore[arg-type]

        def _post(path: str, **kwargs) -> requests.Response:
            resp = requests.post(
                server_url.rstrip("/") + path,
                auth=auth,
                verify=False,
                **kwargs,
            )
            resp.raise_for_status()
            return resp

        # Upload paths are relative to the server basepath, but self.storage is
        # relative to home (i.e. includes the basepath as its first component).
        # Strip the basepath prefix so uploads land in the right place.
        prefix = self._server_basepath.rstrip("/") + "/"
        upload_base = (
            self.storage[len(prefix) :]
            if self.storage.startswith(prefix)
            else self.storage
        )

        # Upload all files in the staging directory
        for local_file in sorted(self.staging_dir.rglob("*")):
            if not local_file.is_file():
                continue
            rel = local_file.relative_to(self.staging_dir)
            server_path = f"{upload_base}/workflow_data/{rel}"
            with local_file.open("rb") as fh:
                _post(
                    "/api/files/upload",
                    files={"file": (local_file.name, fh)},
                    data={"to_file": server_path},
                )

        # Upload rendered_workflow.xml
        xml_bytes = self.to_xml()
        xml_server_path = f"{upload_base}/rendered_workflow.xml"
        _post(
            "/api/files/upload",
            files={"file": ("rendered_workflow.xml", xml_bytes)},
            data={"to_file": xml_server_path},
        )

        # Submit — the server resolves this path against the basepath too
        resp = _post("/api/workflows/submit", json={"filename": xml_server_path})
        data = resp.json()
        if data.get("status") != "submitted":
            raise RuntimeError(f"Workflow submission failed: {data}")
        return xml_server_path


# ---------------------------------------------------------------------------
# Internal: composition tree → Workflow
# ---------------------------------------------------------------------------


def _decompose(
    comp: _Composable,
    predecessors: list[str],
) -> tuple[list[str], list[str], list[tuple[str, list[str], Step]]]:
    """Recursively flatten a composition tree.

    Returns ``(entry_names, exit_names, node_specs)`` where:

    * ``entry_names`` — first node names in this sub-tree (fanout start)
    * ``exit_names``  — last node names in this sub-tree (fanin end)
    * ``node_specs``  — ``[(node_name, predecessor_list, step)]``
    """
    if isinstance(comp, Step):
        return (
            [comp.node_name],
            [comp.node_name],
            [(comp.node_name, predecessors, comp)],
        )

    if isinstance(comp, Chain):
        all_specs: list[tuple[str, list[str], Step]] = []
        current_preds = predecessors
        first_entries: list[str] | None = None
        last_exits: list[str] = predecessors

        for item in comp._items:
            entries, exits, specs = _decompose(item, current_preds)
            if first_entries is None:
                first_entries = entries
            all_specs.extend(specs)
            current_preds = exits
            last_exits = exits

        return first_entries or [], last_exits, all_specs

    if isinstance(comp, Parallel):
        all_specs = []
        all_entries: list[str] = []
        all_exits: list[str] = []

        for branch in comp._branches:
            entries, exits, specs = _decompose(branch, predecessors)
            all_entries.extend(entries)
            all_exits.extend(exits)
            all_specs.extend(specs)

        return all_entries, all_exits, all_specs

    raise TypeError(f"Unknown composition type: {type(comp)!r}")  # type: ignore[unreachable]


def _render_step(
    step: Step,
    staging_dir: Path,
    queueing_system: str,
) -> WorkflowExecModule:
    """Load a WaNo, apply parameter overrides, render into staging_dir."""
    from SimStackServer.WaNo.xml_compat import xml_file_to_spec

    # Find the WaNo XML: prefer a file whose stem matches the directory name,
    # fall back to any single .xml file present.
    xml_candidates = list(step.wano_dir.glob("*.xml"))
    named = [f for f in xml_candidates if f.stem == step.wano_dir.name]
    if named:
        xml_path = named[0]
    elif len(xml_candidates) == 1:
        xml_path = xml_candidates[0]
    else:
        raise FileNotFoundError(
            f"Cannot locate WaNo XML in {step.wano_dir!r}. "
            f"Found: {[f.name for f in xml_candidates]}"
        )

    spec = xml_file_to_spec(xml_path)
    wmr = WaNoModelRoot.from_spec(spec, wano_dir_root=step.wano_dir)
    # from_spec does not load the raw XML tree; populate it so that
    # prepare_files_submission can write the WaNo XML into the staging dir.
    if wmr.full_xml is None:
        wmr.full_xml = etree.parse(str(xml_path)).getroot()
    if step.params:
        wmr.apply_delta_dict(step.params)

    # Evaluate all visibility conditions so that invisible WaNoFile
    # parameters (e.g. conditional restart files) are skipped during render.
    wmr.datachanged_force()

    step_staging = staging_dir / step.node_name
    rendered_wano, _jsdl, wfem, _local_stagein = wmr.render_wano(
        submitdir=str(step_staging),
        stageout_basedir=step.node_name,
    )
    wmr.prepare_files_submission(rendered_wano, str(step_staging))

    wfem._field_values["path"] = step.node_name
    wfem._field_values["wano_xml"] = f"{wmr.name}.xml"
    wfem._field_values["outputpath"] = step.node_name
    wfem.resources.set_field_value("queueing_system", queueing_system)
    return wfem


def _build(
    composition: _Composable,
    name: str,
    storage: str | None,
    queueing_system: str,
) -> BuiltWorkflow:
    now = datetime.datetime.now()
    submit_name = f"{name}_{now.strftime('%Y-%m-%d-%Hh%Mm%Ss')}"
    if storage is None:
        storage = f"simstack_workspace/{submit_name}"

    _, _, node_specs = _decompose(composition, ["0"])
    staging_dir = Path(tempfile.mkdtemp(prefix="simstack_dsl_"))

    # Render every step and collect WFEMs
    name_to_wfem: dict[str, WorkflowExecModule] = {}
    for node_name, _preds, step in node_specs:
        name_to_wfem[node_name] = _render_step(step, staging_dir, queueing_system)

    # Build UID lookup (sentinel "0" stays as "0")
    name_to_uid: dict[str, str] = {n: wfem.uid for n, wfem in name_to_wfem.items()}
    name_to_uid["0"] = "0"

    # Build edge list
    connections: list[tuple[str, str]] = []
    for node_name, preds, _ in node_specs:
        for pred in preds:
            connections.append((name_to_uid[pred], name_to_uid[node_name]))

    # Assemble Workflow
    elements = WorkflowElementList(
        [
            (WorkflowExecModule, name_to_wfem[node_name])
            for node_name, _, _ in node_specs
        ]
    )
    graph = DirectedGraph(connections)

    wf = Workflow()
    wf._field_values["elements"] = elements
    wf._field_values["graph"] = graph
    wf._field_values["storage"] = storage
    wf._field_values["name"] = submit_name
    wf._field_values["submit_name"] = submit_name
    wf._field_values["status"] = int(JobStatus.READY)
    wf._field_values["queueing_system"] = queueing_system

    return BuiltWorkflow(wf, staging_dir, storage)

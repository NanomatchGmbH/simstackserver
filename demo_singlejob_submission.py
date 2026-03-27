#!/usr/bin/env python3
"""
SimStackServer REST API Demonstrator
=====================================
Three demonstrations using WaNos from the test fixtures:

  Demo A — Single job, no external files (bundle API)
      Builds a self-contained WFEM from EmployeeRecord, POSTs it
      directly, polls for status.

  Demo C — Single job with an external input file (bundle API)
      Like Demo A but uses EmployeeRecordWithCV, which has a <WaNoFile>
      parameter.  The script sets the local path on that parameter,
      discovers it via get_external_input_files(), uploads the file
      before submitting, then submits the bundle.

  Demo D — Two-step workflow (WorkflowDSL, Deposit WaNo)
      Composes two Deposit3 simulation steps with deeply nested parameter
      overrides (simulation box size, PBC, conditional post-processing)
      using the Python DSL.

Prerequisites
-------------
1. Start the server (HTTP mode, no auth, port 8080):

       SimStackServer --port 8080 --no-https

   Or with authentication:

       SimStackServer --port 8080 --no-https --username admin --password secret

2. Run this script:

       pixi run python demo_singlejob_submission.py

Configuration
-------------
Edit the constants at the top of the script to match your server setup.
"""

import sys
import time
from pathlib import Path

import requests
from requests.auth import HTTPBasicAuth

# ---------------------------------------------------------------------------
# Configuration – adjust these to match your server
# ---------------------------------------------------------------------------

SERVER_HOST = "127.0.0.1"
SERVER_PORT = 60019
USE_HTTPS = True  # Set True when server is started with HTTPS
USERNAME = "simstack"  # Set to your username string if auth is enabled
PASSWORD = "yuwMhANsprNmR2K3iOSL3Q3rLn2XZApmXVYGf2Aejd3LktjP"  # Set to your password string if auth is enabled

# Path to the EmployeeRecord WaNo directory used by Demo A.
WANO_DIR = Path(__file__).parent / "tests/inputs/wanos/EmployeeRecord"

# WaNo with an external <WaNoFile> parameter (Demo C).
WANO_DIR_WITH_CV = Path(__file__).parent / "tests/inputs/wanos/EmployeeRecordWithCV"

# The CV file that Demo C uploads as an external input.
SAMPLE_CV = Path(__file__).parent / "sample_cv.txt"

# Deposit WaNo with deeply nested parameters (Demo D).
DEPOSIT_WANO_DIR = Path(__file__).parent / "tests/inputs/wanos/Deposit"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SCHEME = "https" if USE_HTTPS else "http"
BASE_URL = f"{SCHEME}://{SERVER_HOST}:{SERVER_PORT}"
AUTH: HTTPBasicAuth | None = (
    HTTPBasicAuth(USERNAME, PASSWORD) if (USERNAME and PASSWORD) else None
)


def get(path: str, **kwargs) -> requests.Response:
    url = BASE_URL + path
    resp = requests.get(url, auth=AUTH, verify=False, **kwargs)
    resp.raise_for_status()
    return resp


def post(path: str, **kwargs) -> requests.Response:
    url = BASE_URL + path
    resp = requests.post(url, auth=AUTH, verify=False, **kwargs)
    resp.raise_for_status()
    return resp


# ---------------------------------------------------------------------------
# Step 1: Health check
# ---------------------------------------------------------------------------


def check_health():
    print("=== Step 1: Server health check ===")
    try:
        data = get("/health").json()
    except requests.exceptions.ConnectionError:
        print(f"  ERROR: Cannot reach server at {BASE_URL}")
        print(
            "  Make sure SimStackServer is running and the configuration above is correct."
        )
        sys.exit(1)
    print(f"  Status       : {data['status']}")
    print(f"  Workflows    : {data.get('workflows_running', '?')} running")
    api_info = get("/").json()
    print(f"  API version  : {api_info.get('api_version', '?')}")
    print()


# ---------------------------------------------------------------------------
# Step 2: Load WaNo and set parameters
# ---------------------------------------------------------------------------


def build_wfem():
    print("=== Step 2: Load WaNo and customise parameters ===")

    # Import here so the script fails loudly if the package isn't installed
    from SimStackServer.WaNo.WaNoModels import WaNoModelRoot

    wmr = WaNoModelRoot(model_only=True, wano_dir_root=WANO_DIR)
    print(f"  Loaded WaNo  : {wmr.name}  (from {WANO_DIR})")

    # ------------------------------------------------------------------
    # Set individual parameters using apply_delta on child nodes.
    # The key path mirrors the XML tree: wmr["ChildName"].apply_delta(value)
    # ------------------------------------------------------------------
    wmr["name"].apply_delta("Alice")
    wmr["Job"].apply_delta("Developer")  # must be one of the dropdown choices

    # Alternatively, set many parameters at once with apply_delta_dict.
    # Keys use dot-separated paths that match the XML nesting:
    #   wmr.apply_delta_dict({"name": "Bob", "Job": "Karen"})

    print(f"  Employee name: {wmr['name'].get_data()}")
    print(f"  Job          : {wmr['Job'].get_data()}")

    # Show any external (user-supplied) files this WaNo needs.
    # EmployeeRecord has none; WaNos that use <WaNoFile> would list them here.
    external = wmr.get_external_input_files()
    if external:
        print("  External files required (must be uploaded separately):")
        for logical_name, local_path in external:
            print(f"    {logical_name}  <-  {local_path}")
    else:
        print("  External files : none (all files are bundled with the WaNo)")
    print()

    # ------------------------------------------------------------------
    # Step 3: Build a self-contained WorkflowExecModule (WFEM)
    # ------------------------------------------------------------------
    print("=== Step 3: Build WFEM with embedded bundle ===")

    # stageout_basedir names the job's output directory on the server.
    wfem = wmr.build_wfem_with_bundle(stageout_basedir="EmployeeRecord_demo")

    # Configure compute resources.  "Internal" uses the server's built-in
    # process pool.  For SLURM/SGE set queueing_system accordingly and fill
    # in base_URI, username, basepath, etc.
    wfem.resources.set_field_value("queueing_system", "Internal")

    print(f"  WFEM uid     : {wfem.uid}")
    print(f"  Exec command : {wfem.exec_command!r}")
    print(f"  Queueing sys : {wfem.resources.queueing_system}")
    bundle_keys = list(wfem._wano_bundle.keys()) if wfem._wano_bundle else []
    print(f"  Bundle files : {bundle_keys}")
    print()

    return wfem


# ---------------------------------------------------------------------------
# Step 4: Upload any external input files
# ---------------------------------------------------------------------------


def upload_external_files(wmr):
    """Upload files marked as external_input (user-supplied scientific data)."""
    external = wmr.get_external_input_files()
    if not external:
        return

    print("=== Step 4: Upload external input files ===")
    for logical_name, local_path in external:
        local_path = Path(local_path)
        if not local_path.exists():
            print(f"  WARN: {local_path} not found – skipping upload")
            continue
        with local_path.open("rb") as fh:
            resp = post(
                "/api/files/upload",
                files={"file": (logical_name, fh)},
                data={"filename": logical_name},
            )
        print(f"  Uploaded {logical_name}: {resp.json().get('message', 'ok')}")
    print()


# ---------------------------------------------------------------------------
# Step 5: Submit the job
# ---------------------------------------------------------------------------


def submit_job(wfem) -> str:
    print("=== Step 5: Submit single job ===")

    # Serialise the WFEM to a plain dict (includes the base64-encoded bundle).
    wfem_dict: dict = {}
    wfem.to_dict(wfem_dict)

    resp = post("/api/singlejobs/submit", json={"wfem": wfem_dict})
    data = resp.json()

    if data.get("status") != "submitted":
        print(f"  ERROR: unexpected response: {data}")
        sys.exit(1)

    job_uid = data["job_uid"]
    print(f"  Status  : {data['status']}")
    print(f"  Message : {data.get('message', '')}")
    print(f"  Job UID : {job_uid}")
    print()
    return job_uid


# ---------------------------------------------------------------------------
# Step 6: Poll for completion
# ---------------------------------------------------------------------------


def wait_for_job(job_uid: str, poll_interval: float = 2.0, timeout: float = 120.0):
    print("=== Step 6: Poll for job completion ===")
    deadline = time.monotonic() + timeout
    dots = 0

    while time.monotonic() < deadline:
        resp = get(f"/api/singlejobs/{job_uid}/status")
        status_data = resp.json()
        # The server returns {"job_uid": ..., "status": {"status": "inprogress"|"finished"}}
        inner = status_data.get("status", {})
        job_status = (
            inner.get("status", "unknown") if isinstance(inner, dict) else str(inner)
        )

        if job_status == "finished":
            print(f"\n  Job finished after ~{dots * poll_interval:.0f}s")
            print()
            return True

        # Print a simple progress indicator
        print(".", end="", flush=True)
        dots += 1
        time.sleep(poll_interval)

    print(f"\n  TIMEOUT: job did not finish within {timeout}s")
    return False


# ---------------------------------------------------------------------------
# Step 7: List output files
# ---------------------------------------------------------------------------


def list_outputs(job_uid: str):
    print("=== Step 7: List output files on server ===")

    # Single jobs are staged under singlejobs/{uid}/ within the server basepath.
    job_path = f"singlejobs/{job_uid}"
    try:
        resp = post("/api/files/list", json={"path": job_path})
        data = resp.json()
        entries = data.get("files", [])
        print(f"  Found {data.get('count', len(entries))} entries in {job_path}/:")
        for entry in entries[:20]:
            marker = "/" if entry.get("type") == "d" else " "
            print(f"    {entry.get('name', '?')}{marker}")
    except requests.exceptions.HTTPError as exc:
        print(f"  Could not list output directory: {exc}")
        print("  (The job ran – check the server's basepath directory manually.)")
    print()


# ---------------------------------------------------------------------------
# Demo C — Single job with an external input file
# ---------------------------------------------------------------------------


def demo_singlejob_with_file():
    """Submit a single job that requires a user-supplied external file.

    EmployeeRecordWithCV has a ``<WaNoFile>`` parameter called ``CV``.
    The intended flow separates discovery from provision:

    1. Load WaNo, set only scalar parameters.
    2. Discover required external files via ``get_external_input_files()``.
       The WaNo still holds placeholder values ("Choose CV file") at this
       point, so the discovery tells the user *what* is needed by logical
       name without requiring any local paths to be known yet.
    3. Provide files: call ``apply_delta("local://<path>")`` on each file
       parameter.  This IS the "provide" step — it stores the local path
       on the model and ensures ``flat_variable_list_to_jsdl`` generates
       the correct server-side stage-in destination.
    4. Build the WFEM bundle (WaNo definition embedded; local file paths
       now correctly reflected in stage-in entries).
    5. Upload each external file to the server path taken from the WFEM's
       own stage-in list — no hard-coding of paths required.
    6. Submit the WFEM; poll for completion.
    """
    from SimStackServer.WaNo.WaNoModels import WaNoModelRoot

    print()
    print("=" * 60)
    print("Demo C — Single job with external input file")
    print("=" * 60)

    if not SAMPLE_CV.exists():
        print(f"  ERROR: sample CV file not found at {SAMPLE_CV}")
        return

    # ------------------------------------------------------------------
    # C1: Load WaNo, set only scalar parameters (no file paths yet)
    # ------------------------------------------------------------------
    print("\n=== C1: Load WaNo and set scalar parameters ===")
    wmr = WaNoModelRoot(model_only=True, wano_dir_root=WANO_DIR_WITH_CV)
    print(f"  Loaded WaNo : {wmr.name}  (from {WANO_DIR_WITH_CV})")
    wmr["name"].apply_delta("Alice")
    wmr["Job"].apply_delta("Developer")

    # ------------------------------------------------------------------
    # C2: Discover which external files the WaNo requires
    #
    # At this point the file parameters still hold their XML placeholder
    # values ("Choose CV file").  The discovery returns the logical
    # filename ("cv.txt") and the current placeholder — enough to know
    # what the user must provide, without needing local paths yet.
    # ------------------------------------------------------------------
    print("\n=== C2: Discover required external files ===")
    needed = wmr.get_external_input_files()
    if not needed:
        print("  ERROR: no external files found — check the WaNo XML")
        return
    for logical_name, placeholder in needed:
        print(f"  Need: {logical_name!r}  (placeholder: {placeholder!r})")

    # ------------------------------------------------------------------
    # C3: Provide files — apply_delta is the "provide" step
    #
    # Calling apply_delta("local://<abs_path>") on a WaNoFile parameter
    # does two things:
    #   a) Stores the local path on the model so the upload step can
    #      read the file.
    #   b) Causes flat_variable_list_to_jsdl to classify the file as an
    #      absolute local import, which makes the WFEM stage-in entry use
    #      the logical_filename as the server-side name (correct behaviour).
    #      Without this call the placeholder string would be used as the
    #      destination filename instead.
    #
    # In a real application you would build a mapping from logical names
    # (returned in step C2) to local Paths and apply them here.
    # ------------------------------------------------------------------
    print("\n=== C3: Provide local paths for required files ===")
    # Mapping: logical_filename -> local Path
    provided: dict[str, Path] = {
        "cv.txt": SAMPLE_CV,
    }
    for logical_name, local_file in provided.items():
        wmr["CV"].apply_delta(f"local://{local_file.resolve()}")
        print(f"  Provided {logical_name!r}  ←  {local_file}")

    # Confirm discovery now reflects the real paths.
    external = wmr.get_external_input_files()

    # ------------------------------------------------------------------
    # C4: Build the self-contained WFEM bundle
    # ------------------------------------------------------------------
    print("\n=== C4: Build WFEM bundle ===")
    wfem = wmr.build_wfem_with_bundle(stageout_basedir="EmployeeRecordWithCV_demo")
    wfem.resources.set_field_value("queueing_system", "Internal")
    print(f"  WFEM uid      : {wfem.uid}")
    print(f"  Exec command  : {wfem.exec_command!r}")
    bundle_keys = list(wfem._wano_bundle.keys()) if wfem._wano_bundle else []
    print(f"  Bundle files  : {bundle_keys}")

    # ------------------------------------------------------------------
    # C5: Upload each external file to the server
    #
    # The server destination comes from the WFEM's own stage-in list —
    # no path hard-coding needed.  Each stage-in entry is a StringList
    # of [logical_name, server_path].
    # ------------------------------------------------------------------
    print("\n=== C5: Upload external input files ===")
    for logical_name, local_path in external:
        local_file = Path(local_path)
        server_dest = None
        for stagein in wfem.inputs:
            pair = list(stagein)
            if len(pair) == 2 and pair[0] == logical_name:
                server_dest = pair[1]
                break
        if server_dest is None:
            print(f"  WARN: no stage-in entry for {logical_name!r}, skipping")
            continue
        # ${STORAGE} is a server-side template placeholder meaning the basepath root;
        # strip it so the upload path is relative to the server basepath.
        upload_dest = server_dest.replace("${STORAGE}/", "")
        with local_file.open("rb") as fh:
            post(
                "/api/files/upload",
                files={"file": (logical_name, fh)},
                data={"to_file": upload_dest},
            )
        print(f"  Uploaded {logical_name!r}  →  {upload_dest}")

    # ------------------------------------------------------------------
    # C6: Submit and poll
    # ------------------------------------------------------------------
    print("\n=== C6: Submit single job ===")
    wfem_dict: dict = {}
    wfem.to_dict(wfem_dict)
    resp = post("/api/singlejobs/submit", json={"wfem": wfem_dict})
    data = resp.json()
    if data.get("status") != "submitted":
        print(f"  ERROR: {data}")
        return
    job_uid = data["job_uid"]
    print(f"  Status  : {data['status']}")
    print(f"  Job UID : {job_uid}")

    print("\n=== C7: Poll for completion ===")
    deadline = time.monotonic() + 120.0
    dots = 0
    while time.monotonic() < deadline:
        inner = get(f"/api/singlejobs/{job_uid}/status").json().get("status", {})
        if isinstance(inner, dict) and inner.get("status") == "finished":
            print(f"\n  Job finished after ~{dots * 2:.0f}s")
            break
        print(".", end="", flush=True)
        dots += 1
        time.sleep(2.0)
    else:
        print(f"\n  TIMEOUT — check: GET {BASE_URL}/api/singlejobs/{job_uid}/status")
        return

    print("\n=== C8: List output directory ===")
    c_job_path = f"singlejobs/{job_uid}"
    try:
        data = post("/api/files/list", json={"path": c_job_path}).json()
        for entry in data.get("files", [])[:20]:
            marker = "/" if entry.get("type") == "d" else " "
            print(f"  {entry.get('name', '?')}{marker}")
    except requests.exceptions.HTTPError as exc:
        print(f"  (list failed: {exc})")
    print()


# ---------------------------------------------------------------------------
# Demo D — Two-step workflow via WorkflowDSL
# ---------------------------------------------------------------------------


def demo_workflow_dsl(poll_interval: float = 2.0, timeout: float = 120.0):
    """Submit a three-step workflow using the WorkflowDSL.

    Demonstrates nested parameter overrides, conditional visibility,
    variable references between steps, and sequential composition.
    The DAG is:

        0 -> InitialDeposit -> ContinuedDeposit -> FinalRecord

    Both Deposit steps use the same Deposit3 WaNo with the same box size.
    The second step restarts from the first step's output by enabling
    "Restart from existing morphology" and referencing
    ``${InitialDeposit/restartfile.zip}`` as the restart file.
    FinalRecord is an EmployeeRecord step appended to confirm that all
    three stages execute in order and that none of them are skipped.
    """
    from SimStackServer.WorkflowDSL import Step

    print()
    print("=" * 60)
    print("Demo D — Two-step workflow via WorkflowDSL (Deposit WaNo)")
    print("=" * 60)

    # ------------------------------------------------------------------
    # D1: Compose two Deposit steps with nested parameter overrides
    #
    # Parameters mirror the WaNo XML hierarchy.  For Deposit3 that is:
    #   TABS
    #   ├── Simulation Parameters
    #   │   ├── Simulation Box  (Lx, Ly, Lz, PBC {enabled, Cutoff})
    #   │   └── Simulation Parameters  (Number of Molecules, …)
    #   ├── Molecules
    #   │   ├── Restart from existing morphology  (bool)
    #   │   └── Restartfile  (WaNoFile, visible when Restart is True)
    #   └── Postprocessing
    #       ├── Extend morphology (x,y)  (bool, controls visibility of ↓)
    #       └── Cut first layer by (A)   (only shown when Extend is True)
    # ------------------------------------------------------------------
    print("\n=== D1: Compose workflow ===")

    # Step 1: initial deposit — 50 molecules, PBC enabled, no restart.
    # "Extend morphology (x,y)" is set to False, so "Cut first layer by (A)"
    # becomes invisible — demonstrating conditional visibility.
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
                "Simulation Parameters": {
                    "Number of Molecules": 50,
                    "Number of Steps": 30000,
                },
            },
            "Postprocessing": {
                "Extend morphology (x,y)": False,
            },
        },
    )

    # Step 2: continued deposit — same box, restarts from step 1's output.
    # "Restart from existing morphology" is True, which makes the
    # "Restartfile" WaNoFile parameter visible.  Its value is a variable
    # reference "${InitialDeposit/restartfile.zip}" that the server resolves
    # at runtime to the first step's output file.
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
                "Simulation Parameters": {
                    "Number of Molecules": 50,
                    "Number of Steps": 60000,
                    "Number of SA cycles": 20,
                },
            },
            "Molecules": {
                "Restart from existing morphology": True,
                "Restartfile": "global://${InitialDeposit/restartfile.zip}",
            },
            "Postprocessing": {
                "Extend morphology (x,y)": True,
                "Cut first layer by (A)": 10.0,
            },
        },
    )

    # Step 3: a minimal EmployeeRecord step appended after both Deposit steps.
    # Its only purpose is to confirm that all three stages execute in order.
    final = Step(
        WANO_DIR,
        node_name="FinalRecord",
        name="PostDepositSummary",
        Job="Karen",
    )

    # Sequential: InitialDeposit -> ContinuedDeposit -> FinalRecord
    pipeline = initial >> continued >> final

    print(f"  Composition : {pipeline}")

    # ------------------------------------------------------------------
    # D2: Build — renders WaNos into a temp staging dir and wires the DAG
    # ------------------------------------------------------------------
    print("\n=== D2: Build workflow ===")
    wf = pipeline.build("demo_dsl_wf")
    print(f"  Storage     : {wf.storage}")
    print(f"  Staging dir : {wf.staging_dir}")

    # ------------------------------------------------------------------
    # D3: Submit — uploads staged files + rendered_workflow.xml, then POSTs
    # ------------------------------------------------------------------
    print("\n=== D3: Submit workflow ===")
    submit_name = wf.storage.split("/")[-1]
    xml_path = wf.submit(
        BASE_URL,
        username=USERNAME,
        password=PASSWORD,
    )
    print(f"  Uploaded XML : {xml_path}")
    print(f"  Submit name  : {submit_name}")

    # ------------------------------------------------------------------
    # D4: Poll until finished; show a status snapshot every ~10 s
    # ------------------------------------------------------------------
    print("\n=== D4: Poll for workflow completion ===")
    deadline = time.monotonic() + timeout
    dots = 0
    last_status_print = time.monotonic()

    while time.monotonic() < deadline:
        finished_data = get("/api/workflows/finished").json()
        finished_names = [w["name"] for w in finished_data.get("workflows", [])]
        if submit_name in finished_names:
            print(f"\n  Workflow finished after ~{dots * poll_interval:.0f}s")
            break

        # Every ~10 s print a brief status snapshot
        if time.monotonic() - last_status_print >= 10.0:
            inprogress = get("/api/workflows/inprogress").json()
            running = [w["name"] for w in inprogress.get("workflows", [])]
            if submit_name in running:
                print(f"\n  [status] workflow '{submit_name}' still in progress …")
            else:
                # Check if it already moved to finished since last check
                if submit_name in [
                    w["name"]
                    for w in get("/api/workflows/finished").json().get("workflows", [])
                ]:
                    print("\n  Workflow finished.")
                    break
                print(
                    f"\n  [status] workflow '{submit_name}' not found in inprogress or finished — may have been aborted"
                )
            last_status_print = time.monotonic()
        else:
            print(".", end="", flush=True)
        dots += 1
        time.sleep(poll_interval)
    else:
        print(f"\n  TIMEOUT: workflow did not finish within {timeout}s")
        inprogress = get("/api/workflows/inprogress").json()
        print(
            f"  Still in progress: {[w['name'] for w in inprogress.get('workflows', [])]}"
        )
        return

    # ------------------------------------------------------------------
    # D5: List output directory
    # ------------------------------------------------------------------
    print("\n=== D5: List output directory on server ===")
    try:
        data = post("/api/files/list", json={"path": wf.upload_base}).json()
        entries = data.get("files", [])
        print(f"  {wf.upload_base}/  ({data.get('count', len(entries))} entries)")
        for entry in entries[:20]:
            marker = "/" if entry.get("type") == "d" else " "
            print(f"    {entry.get('name', '?')}{marker}")
    except requests.exceptions.HTTPError as exc:
        print(f"  Could not list output directory: {exc}")

    print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    print()
    print("SimStackServer REST Demonstrator")
    print("=" * 50)
    print(f"Server : {BASE_URL}")
    print(f"Auth   : {'yes (HTTP Basic)' if AUTH else 'none'}")
    print()

    check_health()

    # --- Demo A: single self-contained job ---
    print("=" * 60)
    print("Demo A — Single job submission")
    print("=" * 60)
    wfem = build_wfem()
    job_uid = submit_job(wfem)
    finished = wait_for_job(job_uid)

    if finished:
        list_outputs(job_uid)
    else:
        print("Demo A timed out – the job may still be running.")
        print(f"  Check: GET {BASE_URL}/api/singlejobs/{job_uid}/status")

    # --- Demo C: single job with external input file ---
    demo_singlejob_with_file()

    # --- Demo D: two-step workflow via WorkflowDSL ---
    demo_workflow_dsl()

    print("All demos complete.")
    print()


if __name__ == "__main__":
    main()

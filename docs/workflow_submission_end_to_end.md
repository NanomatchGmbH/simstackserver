# Workflow Submission — End-to-End Guide

This document describes the complete lifecycle of building and submitting a workflow or a
single job via the SimStackServer REST API.

---

## Concepts

| Term | Meaning |
|------|---------|
| **WaNo** | *Workflow Active Node* — a single computational step. Defined by an XML file that declares parameters, input/output files, and the execution command. Lives in its own directory (`wano_dir_root`). |
| **WaNoModelRoot** | Python object that parses a WaNo XML definition and holds the current parameter state. The authoritative client-side representation of one WaNo. |
| **WorkflowExecModule (WFEM)** | A serialisable job descriptor: holds the rendered exec command, stage-in/out file lists, resource requirements, and (new) the **WaNo bundle**. One WFEM corresponds to one schedulable job. |
| **WaNo bundle** | A `dict[filename -> base64(content)]` embedded in the WFEM that carries the complete WaNo definition (XML, configuration, static input files) so the server needs nothing pre-uploaded. |
| **External input files** | Scientific data files the user must supply. They are *not* part of the WaNo definition and must be uploaded separately before job execution. |
| **Workflow** | A directed acyclic graph of WFEMs with dependency edges. Represented server-side as a `rendered_workflow.xml` file plus a `workflow_data/` directory tree. |

---

## Two submission modes

### Mode A — Single-job (new bundle API)

The simplest path. The client builds one self-contained WFEM and POSTs it.
The server needs no pre-uploaded files for the WaNo definition.

### Mode B — Full workflow (legacy XML file)

The client prepares a `rendered_workflow.xml` and uploads all input files into
`workflow_data/<wano_path>/inputs/` first, then tells the server the filename.
The server walks the DAG and submits each WFEM in dependency order.

---

## Mode A — Single-job end-to-end

### 1. Instantiate the WaNoModelRoot

```python
from SimStackServer.WaNo.WaNoModels import WaNoModelRoot
from pathlib import Path

wano_dir = Path("/path/to/MyWaNo")          # directory containing MyWaNo.xml
wmr = WaNoModelRoot(model_only=True, wano_dir_root=wano_dir)
```

`model_only=True` avoids loading Qt view classes; use without it in a GUI context.

Under the hood `WaNoModelRoot.__init__` calls `_parse_defaults()` which:
1. Calls `xml_compat.xml_file_to_spec()` to convert the WaNo XML to a spec dict.
2. Populates the parameter tree via `_apply_root_spec()`.
3. Reads `imports.yml`, `exports.yml`, `resources.yml` if present.

---

### 2. Set parameter values

Parameters are accessible as a nested tree. Change them before building the WFEM:

```python
# Example: set an integer parameter called "n_atoms"
wmr["Parameters"]["n_atoms"].apply_delta(42)
```

---

### 3. Discover external input files

External input files are scientific data that the WaNo cannot provide itself — e.g.
a molecule geometry, an input structure file, etc. Check what is required:

```python
for logical_name, current_path in wmr.get_external_input_files():
    print(f"  need: {logical_name}  (currently points to: {current_path})")
```

These files must be uploaded to the server **before** the job executes (see step 5).

Alternatively, query the server endpoint without a local `WaNoModelRoot`:

```
POST /api/wano/required-files
Content-Type: application/json

{
  "wano_spec": { ... }   # WaNoModelRoot.to_spec() output
}
```

Response:
```json
{
  "wano_name": "MyWaNo",
  "external_input_files": [
    { "logical_name": "molecule.xyz", "source_path": "/home/user/mol.xyz" }
  ]
}
```

---

### 4. Build the self-contained WFEM

```python
wfem = wmr.build_wfem_with_bundle(stageout_basedir="MyWaNo")
```

Internally this does:
1. **`render_wano(submitdir=None, stageout_basedir=...)`** — two render passes over the
   parameter tree produce a flat `rendered_wano` dict, an exec command string, and
   lists of stage-in/out file paths.
2. **`flat_variable_list_to_jsdl()`** — converts the rendered variable list into a
   `WorkflowExecModule` with `inputs` (stage-in) and `outputs` (stage-out) entries.
3. **`build_bundle()`** — collects:
   - WaNo XML (`{name}.xml`)
   - `wano_configuration.json` (current parameter state as a delta from defaults)
   - `imports.yml`, `exports.yml`, `resources.yml` (if present)
   - All static WaNo-owned files declared in `input_files` (i.e. files that live
     inside `wano_dir_root`)
   Each file is base64-encoded; the result is stored as a JSON string in
   `wfem._wano_bundle`.
4. Sets `wfem.wano_xml = "{name}.xml"`.

The returned WFEM is completely self-contained for the WaNo definition.

---

### 5. Upload external input files

External files must be present at the server path that the WFEM's stage-in entries
reference.  The stage-in source for an absolute-path file is:

```
workflow_data/<stageout_basedir>/inputs/<logical_name>
```

Upload via:

```
POST /api/files/upload
```

with `to_file` set to the relative path above.

---

### 6. Set compute resources

```python
from SimStackServer.WorkflowModel import Resources

resources = Resources()
resources.set_field_value("queueing_system", "Internal")   # or "SLURM", "SGE", …
resources.set_field_value("cpus_per_node", "4")
resources.set_field_value("memory", "8192")
wfem._field_values["resources"] = resources
```

`queueing_system` must not be `"unset"` — the server rejects single jobs without one.

---

### 7. Submit the WFEM

Serialise and POST:

```python
import requests, json

wfem_dict = {}
wfem.to_dict(wfem_dict)

resp = requests.post(
    "https://<server>/api/singlejobs/submit",
    auth=("user", "password"),
    json={"wfem": wfem_dict},
)
job_uid = resp.json()["job_uid"]
```

Endpoint: `POST /api/singlejobs/submit`
Request body: `{"wfem": <dict from wfem.to_dict()>}`
Response: `{"status": "submitted", "job_uid": "<uid>"}`

---

### 8. What the server does on receipt

1. `FastAPIServer` deserialises the dict back into a `WorkflowExecModule` via
   `wfem.from_dict()` — this also restores `_wano_bundle` from the JSON string.
2. The WFEM is placed on `_submitted_singlejob_queue`.
3. The main loop calls `WorkflowManager.start_singlejob(wfem)` which immediately
   calls `wfem.run_jobfile(None)` — no `_prepare_job` for single jobs; the WFEM is
   assumed to be fully rendered already.

> **Note:** Single jobs bypass the `_prepare_job` re-rendering path.  The bundle
> is therefore only needed when the server reconstructs a WaNo during full workflow
> execution (Mode B) or when single jobs require server-side file staging from
> `workflow_data/`.

---

### 9. Poll for status

```
GET /api/singlejobs/<job_uid>/status
```

Returns `{"status": "inprogress"}` or `{"status": "finished"}`.

---

## Mode B — Full workflow end-to-end

### Understanding what needs to go to the server

Before writing any upload code it is important to understand the two-tier file
classification that the upload manifest enforces:

| Category | Examples | Who handles it |
|----------|----------|----------------|
| `wano_definition` | WaNo XML, `wano_configuration.json`, `imports.yml`, static template files | Generated automatically by `prepare_files_submission()` — **no user action needed** |
| `external_input` | molecule geometries, force-field parameters, measured spectra | **User must supply** — these are the only files that can block a submission |

The upload manifest API makes this split explicit so you never have to guess.

---

### 1. Build the upload manifest (before rendering)

Create one `WaNoModelRoot` per workflow node, set parameters, then ask for the
manifest:

```python
from SimStackServer.WaNo.WaNoModels import WaNoModelRoot
from SimStackServer.WaNo.upload_manifest import WorkflowUploadManifest
from pathlib import Path

manifest = WorkflowUploadManifest()

wmr_step1 = WaNoModelRoot(model_only=True, wano_dir_root=Path("/path/to/Relaxation"))
wmr_step2 = WaNoModelRoot(model_only=True, wano_dir_root=Path("/path/to/Analysis"))

# … set parameters on each wmr …

manifest.add_wano(wmr_step1, wfem_path="Relaxation")
manifest.add_wano(wmr_step2, wfem_path="Analysis")

# Human-readable overview
print(manifest.summary())
```

Example output:
```
Workflow upload manifest: 12 total items
  9 wano_definition file(s) — handled automatically
  3 external_input file(s) — must be provided by user

Files YOU must provide:
  [MISSING] Relaxation/molecule.xyz
         local: <not set>
         server: workflow_data/Relaxation/inputs/molecule.xyz
  [OK]     Relaxation/forcefield.dat
         local: /home/alice/ff/uff.dat
         server: workflow_data/Relaxation/inputs/forcefield.dat
  [MISSING] Analysis/spectrum.csv
         local: <not set>
         server: workflow_data/Analysis/inputs/spectrum.csv
```

The manifest can also be queried server-side without a local `WaNoModelRoot`:

```
POST /api/workflows/required-files
Content-Type: application/json

{
  "nodes": [
    { "wano_spec": { ... }, "wfem_path": "Relaxation" },
    { "wano_spec": { ... }, "wfem_path": "Analysis"   }
  ]
}
```

Response fields:
- `required_user_uploads` — the filtered list of `external_input` items; act on these
- `wano_definition_items` — auto-handled; informational only
- `all_items` — combined list
- `summary` — the same human-readable string shown above

---

### 2. Point external inputs to local files and validate

Set the local source path on each `WaNoItemFileModel` parameter, then validate
before rendering:

```python
# Set where the external files live locally
wmr_step1["Inputs"]["molecule"].apply_delta("/home/alice/molecules/ethanol.xyz")

# Validate — raises FileNotFoundError listing every missing file
manifest = WorkflowUploadManifest()
manifest.add_wano(wmr_step1, "Relaxation")
manifest.add_wano(wmr_step2, "Analysis")
manifest.validate()   # fails early if any external_input file is missing locally
```

This is the correct place to catch missing files — before any rendering or upload
has started.

---

### 3. Render each WaNo and prepare the submission tree

```python
basefolder = Path("/tmp/my_workflow_staging")

for wmr, node_path in [(wmr_step1, "Relaxation"), (wmr_step2, "Analysis")]:
    node_staging = basefolder / node_path
    rendered_wano, _jsdl, wem, _local = wmr.render_wano(
        submitdir=str(node_staging),
        stageout_basedir=node_path,
    )
    wmr.prepare_files_submission(rendered_wano, str(node_staging))
```

After this step `basefolder/<node_path>/inputs/` contains **everything** — both
`wano_definition` and `external_input` files — ready to be uploaded.

`prepare_files_submission` writes:
- `inputs/{name}.xml` — WaNo XML
- `inputs/wano_configuration.json` — current parameter state
- `inputs/imports.yml`, `exports.yml`, `resources.yml` — when non-default
- All WaNo-owned static files listed in `input_files`

`render_wano(submitdir=...)` additionally copies `WaNoItemFileModel` local files
(the `external_input` category) into `inputs/` — which is why `validate()` must
be called before this step.

---

### 4. Upload the staging tree to the server

```python
import requests

for node_path in ["Relaxation", "Analysis"]:
    local_dir  = str(basefolder / node_path / "inputs")
    server_dir = f"workflow_data/{node_path}/inputs"
    requests.post(
        "https://<server>/api/files/put-directory",
        auth=("user", "password"),
        json={"from_directory": local_dir, "to_directory": server_dir},
    )
```

If you only need to upload individual files (e.g. when re-running with a changed
input file):

```python
requests.post(
    "https://<server>/api/files/upload",
    auth=("user", "password"),
    files={"file": open("/local/molecule.xyz", "rb")},
    data={"to_file": "workflow_data/Relaxation/inputs/molecule.xyz"},
)
```

---

### 5. Assemble the Workflow object

The `Workflow` object (`WorkflowModel.Workflow`) holds:
- `elements` — a flat `WorkflowElementList` of all WFEMs
- `graph` — a `DirectedGraph` encoding dependency edges
- `storage` — absolute path on the server where all workflow data lives
- `submit_name` — unique identifier for this workflow run

The assembled workflow is serialised to `rendered_workflow.xml` and uploaded to
`<storage>/rendered_workflow.xml` on the server.

---

### 6. Submit the workflow filename

```python
resp = requests.post(
    "https://<server>/api/workflows/submit",
    auth=("user", "password"),
    json={"filename": "relative/path/to/rendered_workflow.xml"},
)
```

The path is interpreted relative to the server's home directory if not absolute.

---

### 5. Server-side execution loop

1. `SimStackServer.main_loop` picks the filename from `_submitted_workflow_queue`.
2. `WorkflowManager.start_wf()` calls `Workflow.new_instance_from_xml()` to parse
   `rendered_workflow.xml` into a `Workflow` object, then adds it to
   `_inprogress_models`.
3. Every ~3 s `WorkflowManager.check_status_submit()` calls `workflow.jobloop()`.
4. `jobloop()` asks the `DirectedGraph` for the next ready nodes and calls
   `_prepare_job(wfem)` for each.

#### Inside `_prepare_job(wfem)`

1. Creates a timestamped `exec_directories/<name>/` under `storage`.
2. Resolves `wano_dir_root = storage/workflow_data/<wfem.path>/inputs/`.
3. **Calls `_unpack_wano_bundle(wfem, wano_dir_root)`** — if the WFEM carries a
   bundle, writes all files there.  Otherwise falls back to the files already on
   disk (backward-compatible with pre-bundle workflows).
4. Reconstructs `WaNoModelRoot.from_spec(xml_file_to_spec(wano_dir_root / wfem.wano_xml), ...)`.
5. Reads `wano_configuration.json` via `wmr.read(wano_dir_root)`.
6. Performs two render passes over the WaNo parameter tree, substituting values
   from `_input_variables` (outputs of upstream WaNos) and `runtime_variables`.
7. Renders the exec command from its Jinja template.
8. Writes `rendered_wano.yml` to the job directory.
9. In secure mode, validates the rendered parameters against the approved WaNo schema.
10. Copies / templates all stage-in files into the job directory.
11. Calls `wfem.run_jobfile()` to submit to the batch system (Internal, SLURM, SGE, …).

---

### 6. Post-job care

When `wfem.completed_or_aborted()` becomes true:

1. For remote jobs: downloads the runtime directory via SSH.
2. Scans expected output files; registers them in `_output_variables` so downstream
   WaNos can reference them.
3. Stores results in the `ResultRepo` (keyed by input hash for result reuse).
4. When all nodes finish, `Workflow.finalize()` generates the HTML workflow report.

---

## Directory layout on the server

```
<storage>/
├── rendered_workflow.xml          # full workflow definition (Mode B)
├── workflow_report.html           # generated after completion
├── workflow_data/
│   └── <node_path>/
│       └── inputs/                # WaNo XML, config, static files
│           ├── MyWaNo.xml
│           ├── wano_configuration.json
│           ├── imports.yml
│           └── <static_input_files>
└── exec_directories/
    └── <timestamp>-<name>/        # per-run job directory
        ├── rendered_wano.yml
        ├── <input_files_copied_here>
        └── <output_files>
```

---

## REST API quick reference

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/api/singlejobs/submit` | Submit a single self-contained WFEM |
| `GET`  | `/api/singlejobs/{uid}/status` | Poll single-job status |
| `POST` | `/api/singlejobs/{uid}/abort` | Abort a running single job |
| `POST` | `/api/wano/required-files` | Query external files required by one WaNo spec |
| `POST` | `/api/workflows/required-files` | Upload manifest for a full workflow — identifies `wano_definition` vs `external_input` files |
| `POST` | `/api/workflows/submit` | Submit a full workflow by server-side filename |
| `GET`  | `/api/workflows` | List all workflows |
| `GET`  | `/api/workflows/inprogress` | List in-progress workflows |
| `GET`  | `/api/workflows/finished` | List finished workflows |
| `POST` | `/api/workflows/{id}/abort` | Abort a workflow |
| `POST` | `/api/workflows/{id}/delete` | Delete a workflow and its files |
| `POST` | `/api/wano/required-files` | Query external files required by a WaNo spec |
| `POST` | `/api/files/upload` | Upload a file to the server |
| `GET`  | `/api/files/download` | Download a file from the server |
| `POST` | `/api/files/mkdir` | Create a directory |
| `POST` | `/api/files/put-directory` | Upload a whole directory tree |
| `POST` | `/api/configure` | Set server resource configuration |
| `POST` | `/api/server/shutdown` | Gracefully shut down the server |

# SimStackServer

SimStackServer is the server component of the SimStack workflow system developed by Nanomatch GmbH. It manages and executes computational workflows containing "WaNos" (Workflow Active Nodes), designed for scientific computing and simulation tasks.

## Features

- **Workflow Management**: Executes and monitors computational workflows through a daemon process
- **Distributed Computing**: Client-server architecture with ZeroMQ for communication
- **Cluster Support**: Runs workflows on local and remote compute clusters
- **Job Management**: Handles jobs in various states (queued, running, finished, failed)
- **Security**: Implements security features for running secure workflows
- **Web Interface**: Includes an HTTP server for serving workflow results and reports
- **Resource Handling**: Manages computational resources and job scheduling

## Installation

SimStackServer can be installed using using micromamba:

```bash
micromamba install -c https://mamba.nanomatch-distribution.de/mamba-repo -c conda-forge simstackserver
```

## Usage

### Starting the Server

To start the SimStackServer daemon:

```bash
SimStackServer
```

### Stopping the Server

To stop the running SimStackServer daemon:

```bash
KillSimStackServer
```

### Workflow Composition DSL

`SimStackServer.WorkflowDSL` provides a Python-native API for composing workflows
without writing XML or managing UUIDs by hand.

```python
from SimStackServer.WorkflowDSL import Step, foreach

WANO_DIR = "path/to/MyWaNo"   # directory containing MyWaNo.xml

# --- Flat parameters (simple WaNos) ---
step = Step(WANO_DIR, node_name="Run1", name="Alice", Job="Developer")
wf = step.build("my_workflow")

# --- Nested parameters (complex WaNos) ---
# Keyword arguments mirror the WaNo XML hierarchy as nested dicts.
step = Step(
    "path/to/Deposit",
    node_name="Sim",
    TABS={
        "Simulation Parameters": {
            "Simulation Box": {"Lx": 80.0, "Ly": 80.0, "Lz": 80.0,
                               "PBC": {"enabled": True, "Cutoff": 40.0}},
            "Simulation Parameters": {"Number of Molecules": 50},
        },
        "Postprocessing": {"Extend morphology (x,y)": False},
    },
)

# --- Variable references (wire outputs to inputs) ---
# Use "global://${NodeName/output_file}" to reference another step's output.
initial = Step("path/to/Deposit", node_name="InitialDeposit",
               TABS={"Simulation Parameters": {"Simulation Box": {"Lx": 80.0}}})
continued = Step("path/to/Deposit", node_name="ContinuedDeposit",
                 TABS={"Molecules": {
                     "Restart from existing morphology": True,
                     "Restartfile": "global://${InitialDeposit/restartfile.zip}",
                 }})
wf = (initial >> continued).build("restart_wf")

# --- Sequential (step_a runs first, then step_b) ---
wf = (step_a >> step_b).build("sequential_wf")

# --- Parallel (step_a and step_b run simultaneously, then step_c joins) ---
wf = ((step_a & step_b) >> step_c).build("parallel_wf")

# --- Fan-out over a list ---
names = ["Alice", "Bob", "Eve"]
fan = foreach(names, lambda n: Step(WANO_DIR, node_name=n, name=n))
wf = fan.build("fanout_wf")

# --- Submit to a running server ---
wf.submit("http://localhost:8080")
# With authentication:
wf.submit("http://localhost:8080", username="admin", password="secret")
```

`>>` chains steps sequentially; `&` runs them in parallel.
Any combination can be arbitrarily nested:

```python
wf = (step_a >> (step_b & step_c) >> step_d).build("complex_wf")
```

See `demo_singlejob_submission.py` for a runnable end-to-end example (Demo D).

## Docker

Docker support files live in the `docker/` subdirectory:

| File | Purpose |
|---|---|
| `docker/Dockerfile` | Builds the server image (build context is the project root) |
| `docker/docker-compose.yml` | Runs the server; configure via environment variables |

**Build the image:**

```bash
pixi run docker-build
# or directly:
docker build -f docker/Dockerfile -t simstackserver:latest .
```

**Start with docker compose:**

```bash
pixi run docker-up
# or directly:
docker compose -f docker/docker-compose.yml up
```

**Stop:**

```bash
pixi run docker-down
```

### Configuration via environment variables

All server settings are controlled by `SIMSTACK_*` environment variables defined
in `docker/docker-compose.yml`. No config file mount is required.

| Variable | Default | Description |
|---|---|---|
| `SIMSTACK_SERVER_PORT` | `8000` | REST API port (must match the `ports:` mapping) |
| `SIMSTACK_SERVER_SECRET` | `changeme` | Password for HTTP Basic authentication — **change this** |
| `SIMSTACK_BASEPATH` | `simstack_workspace` | Workflow data directory (relative to container home) |
| `SIMSTACK_QUEUEING_SYSTEM` | `Internal` | Queuing system (`Internal`, `slurm`, `sge`, …) |
| `SIMSTACK_CPUS_PER_NODE` | `1` | CPUs available per node |
| `SIMSTACK_NODES` | `1` | Number of nodes |
| `SIMSTACK_MEMORY` | `4096` | Memory in MB |
| `SIMSTACK_WALLTIME` | `86399` | Walltime in seconds |
| `SIMSTACK_QUEUE` | `default` | Queue name |
| `SIMSTACK_RESOURCE_NAME` | `<Connected Server>` | Display name for the resource |

Advanced / remote-cluster variables (commented out in `docker-compose.yml`):
`SIMSTACK_BASE_URI`, `SIMSTACK_USERNAME`, `SIMSTACK_SSH_PORT`, `SIMSTACK_SSH_KEY`,
`SIMSTACK_RESOURCE_SECRET`, `SIMSTACK_USE_SSH_TUNNEL`, `SIMSTACK_SW_DIR`,
`SIMSTACK_EXTRA_CONFIG`, `SIMSTACK_CUSTOM_REQUESTS`, `SIMSTACK_SGE_PE`,
`SIMSTACK_REUSE_RESULTS`, `SIMSTACK_RESOURCE_REST_PORT`.

Environment variables override any values already persisted in the server's
config file, so they take effect on every container start.

### Volumes

| Mount | Purpose |
|---|---|
| `./simstack_workspace` | Workflow data; must match `SIMSTACK_BASEPATH` |
| `./certs` | TLS certificates (`~/.simstack/certs/`); persisted so clients don't need to re-trust after container restarts |

Both directories are created automatically on first run.

## Development

### Prerequisites

- Python 3.11 or higher
- Pixi (for dependency management)

### Setup Development Environment

Clone the repository:

```bash
git clone https://github.com/NanomatchGmbH/simstackserver.git
cd simstackserver
```

Set up the development environment with Pixi:

```bash
pixi install
```

### Running Tests

```bash
pixi run tests
```

### Linting

```bash
pixi run lint
```

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Contact

For questions or support, contact info@nanomatch.com or visit [https://github.com/NanomatchGmbH/simstackserver](https://github.com/NanomatchGmbH/simstackserver)

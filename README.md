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

## Dependencies

Key dependencies include:
- ZeroMQ for communication
- NetworkX for workflow representation
- Paramiko for SSH connections
- Jinja2 for templating
- SQLAlchemy for database operations
- Lxml for XML processing
- Python-daemon for daemon process management

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Contact

For questions or support, contact info@nanomatch.com or visit [https://github.com/NanomatchGmbH/simstackserver](https://github.com/NanomatchGmbH/simstackserver)

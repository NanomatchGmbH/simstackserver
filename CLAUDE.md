# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

### Environment Setup
```bash
pixi install              # Install dependencies
```

### Testing
```bash
pixi run tests           # Run all tests with coverage
pixi run tests PYTESTOPTIONS  # Run specific tests (e.g., pixi run tests tests/test_specific.py)
```

### Code Quality
```bash
pixi run lint            # Run linting and pre-commit hooks
pixi run pre-commit-run  # Run pre-commit hooks only
pixi run mypy            # Run type checking
```

### Building
```bash
pixi run pythonbuild     # Build Python package
pixi run condabuild      # Build conda package
```

## Architecture Overview

SimStackServer is a distributed workflow management system for scientific computing, built around these core components:

### Core Server Components
- **SimStackServerMain.py**: Main server daemon that handles ZeroMQ communication and workflow orchestration
- **SimStackServerEntryPoint.py**: Entry point that sets up daemon process, PID files, and server configuration
- **ClusterManager.py**: Manages remote compute clusters via SSH, handles job submission and monitoring
- **LocalClusterManager.py**: Handles local job execution without SSH
- **RemoteServerManager.py**: Manages file transfers and communication with remote servers

### Workflow Engine
- **WorkflowModel.py**: Core workflow representation using NetworkX graphs, handles workflow execution state
- **WaNo/**: Workflow Active Node system - individual computational steps in workflows
  - **WaNoModels.py**: WaNo configuration and execution models
  - **WaNoFactory.py**: Creates WaNo instances from XML definitions
  - **WaNoTreeWalker.py**: Traverses and processes WaNo hierarchies
- **EvalHandler.py**: Evaluates expressions and variables in workflow contexts

### Communication & Protocols
- **MessageTypes.py**: Defines ZeroMQ message types and job status enums
- **HTTPServer/**: Web interface for serving workflow results and reports
- Uses ZeroMQ for client-server communication with authentication

### Job Management
- **BaseClusterManager.py**: Abstract base for cluster management implementations
- **InternalBatchSystem.py**: Internal job queuing and execution system
- Integrates with external queueing systems (SGE, SLURM, etc.)

### Security & Configuration
- **SecureWaNos.py**: Security framework for safe workflow execution
- **Config.py**: Configuration management and environment setup
- **Settings/**: Cluster and system configuration providers

### Utilities
- **Util/**: Helper modules for file operations, XML processing, networking, exceptions
- **Reporting/**: HTML report generation from workflow results
- **Tools/**: Command-line utilities (server control, JSON schema generation)

## Key Workflow Concepts

**WaNos (Workflow Active Nodes)**: Individual computational steps that can be chained together. Each WaNo has:
- XML definition file describing inputs/outputs
- Execution scripts
- Resource requirements
- Input/output variable mappings

**Workflows**: Directed acyclic graphs of WaNos, represented using NetworkX, with dependency management and parallel execution capabilities.

**Execution Model**: Workflows are submitted to the server, which manages execution across local and remote compute resources, with job queuing, monitoring, and result collection.

## Testing Structure

Tests are organized by component in `tests/` with integration tests for workflow execution, cluster management, and WaNo processing. Test data is in `tests/input_dirs/` and `tests/inputs/`.

## Entry Points

The system provides these command-line tools:
- `SimStackServer`: Start the daemon
- `KillSimStackServer`: Stop the daemon
- `SimStack_generate_json_schema`: Generate JSON schemas for WaNos

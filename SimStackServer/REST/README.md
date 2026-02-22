# SimStackServer REST API

This directory contains the FastAPI-based REST API for SimStackServer workflow management.

## Installation

The REST API dependencies (fastapi, uvicorn, pydantic) are included in the main project dependencies in `pyproject.toml`.

To install all dependencies including the REST API:

```bash
pixi install
```

## Running the API

To run the FastAPI server:

```bash
uvicorn SimStackServer.REST.workflows_api:app --reload --host 0.0.0.0 --port 8000
```

## Available Endpoints

### Workflows

- **POST /workflows** - Create a new workflow
- **GET /workflows** - Get list of all workflows (with pagination and filtering)
- **GET /workflows/{workflow_id}** - Get a specific workflow by ID
- **PUT /workflows/{workflow_id}** - Update an existing workflow
- **DELETE /workflows/{workflow_id}** - Delete a workflow

### Workflow Operations

- **POST /workflows/{workflow_id}/submit** - Submit a workflow for execution
- **POST /workflows/{workflow_id}/abort** - Abort a running workflow
- **GET /workflows/{workflow_id}/status** - Get the current status of a workflow
- **GET /workflows/{workflow_id}/jobs** - Get all jobs associated with a workflow

## API Documentation

Once the server is running, you can access:

- **Interactive API docs (Swagger UI)**: http://localhost:8000/docs
- **Alternative API docs (ReDoc)**: http://localhost:8000/redoc
- **OpenAPI schema**: http://localhost:8000/openapi.json

## Usage Examples

### Create a workflow

```bash
curl -X POST "http://localhost:8000/workflows" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "my_workflow",
    "description": "Test workflow",
    "workflow_data": {"key": "value"}
  }'
```

### Get all workflows

```bash
curl -X GET "http://localhost:8000/workflows"
```

### Get a specific workflow

```bash
curl -X GET "http://localhost:8000/workflows/{workflow_id}"
```

### Submit a workflow

```bash
curl -X POST "http://localhost:8000/workflows/{workflow_id}/submit"
```

### Delete a workflow

```bash
curl -X DELETE "http://localhost:8000/workflows/{workflow_id}"
```

#!/usr/bin/env python3
"""Export OpenAPI specification to JSON file."""

import json
from pathlib import Path

from prediction_data.api.main import app

# Export to repo root
output_path = Path(__file__).parent.parent / "openapi.json"

openapi_schema = app.openapi()
with open(output_path, "w") as f:
    json.dump(openapi_schema, f, indent=2)

print(f"OpenAPI spec exported to {output_path}")

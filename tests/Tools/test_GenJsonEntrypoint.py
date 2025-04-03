import os
import sys
from unittest.mock import patch, mock_open, MagicMock

from SimStackServer.Tools.GenJsonEntrypoint import add_additional_properties, main

# Add SimStackServer to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))


class TestGenJsonEntrypoint:
    def test_add_additional_properties(self):
        # Test data with nested objects
        test_data = {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "nested": {
                    "type": "object",
                    "properties": {"value": {"type": "number"}},
                },
                "array": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {"id": {"type": "string"}},
                    },
                },
            },
        }

        # Call function to modify the schema
        result = add_additional_properties(test_data)

        # Check top-level additionalProperties is added
        assert result["additionalProperties"] is False

        # Check nested object additionalProperties is added
        assert result["properties"]["nested"]["additionalProperties"] is False

        # Check array item additionalProperties is added
        assert result["properties"]["array"]["items"]["additionalProperties"] is False

    def test_add_additional_properties_non_object(self):
        # Test with non-object type
        test_data = {"type": "string"}
        result = add_additional_properties(test_data)
        assert result is None
        test_data = {"type": "object", "properties": {"key": "value"}}
        result = add_additional_properties(test_data)
        # No additionalProperties should be added
        assert result["additionalProperties"] is False
        assert result["type"] == test_data["type"]
        assert result["properties"] == test_data["properties"]

    @patch(
        "builtins.open",
        new_callable=mock_open,
        read_data='{"name": "test", "value": 123}',
    )
    @patch("yaml.safe_load")
    @patch("json.dumps")
    @patch("SimStackServer.Tools.GenJsonEntrypoint.SchemaBuilder")
    def test_main_function(
        self, mock_builder, mock_json_dumps, mock_yaml_load, mock_file
    ):
        # Setup mock return for yaml.safe_load
        mock_yaml_load.return_value = {"name": "test", "value": 123}

        # Setup mock return for SchemaBuilder
        mock_builder_instance = MagicMock()
        mock_builder_instance.add_object.return_value = None
        mock_builder_instance.add_object.to_schema.return_value = {
            "type": "object",
            "properties": {"name": {"type": "string"}, "value": {"type": "integer"}},
        }
        mock_builder.return_value = mock_builder_instance

        # Call main function
        main()

        # Verify yaml was loaded
        mock_yaml_load.assert_called_once()

        # Verify schema was built
        mock_builder_instance.add_object.assert_called_once()
        mock_builder_instance.to_schema.assert_called_once()

        # Verify additionalProperties was added and JSON was dumped
        mock_json_dumps.assert_called_once()

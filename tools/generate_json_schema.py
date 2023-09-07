import yaml
import json
from genson import SchemaBuilder

if __name__ == '__main__':
    with open("output_dict.yml", "r") as infile:
        content = yaml.safe_load(infile)

    builder = SchemaBuilder()
    builder.add_object(content)

print(json.dumps(builder.to_schema(), indent=2))

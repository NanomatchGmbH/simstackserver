import yaml
import json
from genson import SchemaBuilder
from TreeWalker.TreeWalker import TreeWalker

def add_additional_properties(subdict):
    sd_type = subdict.get("type", "not_object")
    if sd_type == "object":
        subdict["additionalProperties"] = False
        walker = TreeWalker(subdict["properties"])
        subdict["properties"] = walker.walker(
            path_visitor_function=None,
            data_visitor_function=None,
            subdict_visitor_function = add_additional_properties, capture=True)
        return subdict
    return None


if __name__ == '__main__':
    with open("output_dict.yml", "r") as infile:
        content = yaml.safe_load(infile)

    builder = SchemaBuilder()
    builder.add_object(content)

    no_add_properties_schema = builder.to_schema()
    tw = TreeWalker(no_add_properties_schema)
    add_properties_schema = tw.walker(path_visitor_function=None,
              data_visitor_function=None,
              subdict_visitor_function=add_additional_properties,
              capture=True)
    print(json.dumps(add_properties_schema, indent=2))

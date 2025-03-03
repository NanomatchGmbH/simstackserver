#!/usr/bin/python
# -*- coding: utf-8 -*-

# from pyura.pyura.helpers import trace_to_logger
import json
import logging
import pathlib
import re
from functools import partial
from json import JSONDecodeError
from os.path import join, isabs
from pathlib import Path
from typing import Optional, Dict, Any

import jsonschema
import numpy as np

from SimStackServer.Reporting.ReportRenderer import ReportRenderer
from SimStackServer.Util.Exceptions import SecurityError
from SimStackServer.Util.XMLUtils import is_regular_element
from SimStackServer.WaNo.MiscWaNoTypes import (
    WaNoListEntry,
    get_wano_xml_path,
    WaNoListEntry_from_folder_or_zip,
)
from SimStackServer.WaNo.WaNoDelta import WaNoDelta
from SimStackServer.WorkflowModel import (
    WorkflowExecModule,
    StringList,
    WorkflowElementList,
    Resources,
)

import collections

from nestdictmod.nestdictmod import NestDictMod, EraseEntryError
from SimStackServer.WaNo.AbstractWaNoModel import (
    AbstractWanoModel,
    OrderedDictIterHelper,
)
import SimStackServer.WaNo.WaNoFactory
from lxml import etree
import xmltodict
import copy

import yaml
import os
import sys
import shutil
import ast

from jinja2 import Template

from SimStackServer.WaNo.WaNoExceptions import WorkflowSubmitError


from SimStackServer.WaNo.WaNoTreeWalker import (
    PathCollector,
    subdict_skiplevel,
    subdict_skiplevel_to_type,
    subdict_skiplevel_to_aiida_type,
    WaNoTreeWalker,
)
from nestdictmod.flatten_dict import flatten_dict
from nestdictmod.tree_list_to_dict import tree_list_to_dict, tree_list_to_dict_multiply


class FileNotFoundErrorSimStack(FileNotFoundError):
    pass


class WaNoParseError(Exception):
    pass


def mkdir_p(path):
    import errno

    try:
        os.makedirs(path)
    except OSError as exc:  # Python >2.5
        if exc.errno == errno.EEXIST and os.path.isdir(path):
            pass
        else:
            raise


class WaNoModelDictLike(AbstractWanoModel):
    def __init__(self, *args, **kwargs):
        super(WaNoModelDictLike, self).__init__(*args, **kwargs)
        self.wano_dict = OrderedDictIterHelper()

    def parse_from_xml(self, xml):
        self.xml = xml
        for child in self.xml:
            if not is_regular_element(child):
                continue
            name = child.attrib["name"]
            ModelClass = SimStackServer.WaNo.WaNoFactory.WaNoFactory.get_model_class(
                child.tag
            )
            ViewClass = SimStackServer.WaNo.WaNoFactory.WaNoFactory.get_qt_view_class(
                child.tag
            )
            model = ModelClass()
            model.set_view_class(ViewClass)
            model.set_name(name)
            model.parse_from_xml(child)
            self.wano_dict[name] = model
        super().parse_from_xml(xml)

    @property
    def dictlike(self):
        return True

    def __getitem__(self, item):
        return self.wano_dict[item]

    def keys(self):
        return self.wano_dict.keys()

    def values(self):
        return self.wano_dict.values()

    def items(self):
        return self.wano_dict.items()

    def __iter__(self):
        return iter(self.wano_dict)

    def changed_from_default(self) -> bool:
        return False

    def get_data(self):
        return self.wano_dict

    def set_data(self, wano_dict):
        self.wano_dict = wano_dict

    def get_secure_schema(self) -> Optional[str]:
        child_properties_dict = {}
        oneOf_properties_dict = None
        required_keys = []
        number_of_switches = 0
        for wano_name, wano_element in self.wano_dict.items():
            if isinstance(wano_element, WaNoSwitchModel):
                number_of_switches += 1
                if number_of_switches == 2:
                    raise NotImplementedError(
                        "Only a single switch supported per DictBox"
                    )
                oneOf_properties_dict = wano_element.get_secure_schema()
                continue

            required_keys.append(wano_name)
            secure_schema = wano_element.get_secure_schema()
            if secure_schema:
                child_properties_dict.update(secure_schema)
            else:
                raise NotImplementedError(
                    f"missing_{wano_element.__class__} secure schema generator"
                )

        properties_dict = {
            self.name: {
                "type": "object",
                "properties": child_properties_dict,
                "required": required_keys,
                "additionalProperties": False,
            },
        }
        if oneOf_properties_dict:
            properties_dict[self.name].update(oneOf_properties_dict)
        return properties_dict

    def wanos(self):
        return self.wano_dict.values()

    def set_parent_visible(self, is_visible):
        super().set_parent_visible(is_visible)
        if self._isvisible:
            for model in self.wanos():
                model.set_parent_visible(is_visible)

    def set_visible(self, is_visible):
        super().set_visible(is_visible)
        for model in self.wanos():
            model.set_parent_visible(is_visible)

    def get_type_str(self):
        return "Dict"

    # def __repr__(self):
    #    return repr(self.wano_dict)

    def update_xml(self):
        for wano in self.wano_dict.values():
            wano.update_xml()

    def decommission(self):
        for wano in self.wano_dict.values():
            wano.decommission()
        super().decommission()


class WaNoChoiceModel(AbstractWanoModel):
    def __init__(self, *args, **kwargs):
        super(WaNoChoiceModel, self).__init__(*args, **kwargs)
        self.choices = []
        self.chosen = 0
        self._default = 0

    def parse_from_xml(self, xml):
        super().parse_from_xml(xml)
        self.xml = xml
        for child in self.xml.iter("Entry"):
            if not is_regular_element(child):
                continue
            myid = int(child.attrib["id"])
            self.choices.append(child.text)
            assert len(self.choices) == myid + 1
            if "chosen" in child.attrib:
                if child.attrib["chosen"].lower() == "true":
                    self.chosen = myid
                    self._default = self.chosen

    def __getitem__(self, item):
        return None

    def get_type_str(self):
        return "String"

    def get_data(self):
        try:
            return self.choices[self.chosen]
        except IndexError:
            print("Invalid choice in %s. Returning choice 0" % self.name)
            return self.choices[0]

    def changed_from_default(self) -> bool:
        return self._default != self.chosen

    def get_delta_to_default(self):
        return self.choices[self.chosen]

    def apply_delta(self, delta):
        self.chosen = self.choices.index(delta)
        self.set_data(self.choices[self.chosen])

    def set_chosen(self, choice):
        self.chosen = int(choice)
        self.set_data(self.choices[self.chosen])

    def update_xml(self):
        for child in self.xml.iter("Entry"):
            if not is_regular_element(child):
                continue
            myid = int(child.attrib["id"])
            if "chosen" in child.attrib:
                del child.attrib["chosen"]

            if self.chosen == myid:
                child.attrib["chosen"] = "True"

    def get_secure_schema(self) -> Optional[str]:
        schema = {
            self.name: {
                "enum": self.choices,
            }
        }
        return schema


# ToDo: Timo I could not find any usage of DynamicChoiceModel in any Nanomatch-WaNo
class WaNoDynamicChoiceModel(WaNoChoiceModel):
    def __init__(self, *args, **kwargs):
        super(WaNoDynamicChoiceModel, self).__init__(*args, **kwargs)
        self._collection_path = ""
        self._subpath = ""
        self.choices = ["uninitialized"]
        self.chosen = -1
        self._connected = True
        self._updating = False
        self._registered = False
        self._registered_paths = []
        self._delayed_delta_apply = None

    def parse_from_xml(self, xml):
        super().parse_from_xml(xml)
        self.xml = xml
        self._collection_path = self.xml.attrib["collection_path"]
        self._subpath = self.xml.attrib["subpath"]
        self.choices = ["uninitialized"]
        self.chosen = int(self.xml.attrib["chosen"])
        self._connected = True
        self._updating = False

    def set_root(self, root):
        super().set_root(root)
        self._connected = True
        if not self._registered:
            # print(f"I am registering with {root} {self.path}")
            root.register_callback(
                self._collection_path,
                self._update_choices,
                self._collection_path.count("."),
            )
            self._registered = True

    def _update_choices(self, changed_path):
        if not self._connected:
            return
        if (
            not changed_path.startswith(self._collection_path)
            and not changed_path == "force"
        ):
            return

        self._updating = True
        wano_listlike = self._root.get_value(self._collection_path)
        self.choices = []
        numchoices = len(wano_listlike)
        register_paths = []
        for myid in range(0, numchoices):
            query_string = "%s.%d.%s" % (self._collection_path, myid, self._subpath)
            register_paths.append(query_string)
            self.choices.append(self._root.get_value(query_string).get_data())

        delete_later = []
        for path in self._registered_paths:
            if path not in register_paths:
                self._root.unregister_callback(
                    path, self._update_choices, self.path_depth()
                )
                delete_later.append(path)
        for path in delete_later:
            self._registered_paths.remove(path)

        for path in register_paths:
            if path in self._registered_paths:
                continue
            self._root.register_callback(path, self._update_choices, self.path_depth())
            self._registered_paths.append(path)

        if len(self.choices) == 0:
            self.choices = ["uninitialized"]

        if len(self.choices) <= self.chosen:
            self.chosen = 0

        self._updating = False

        if self._delayed_delta_apply:
            super().apply_delta(self._delayed_delta_apply)
            self._delayed_delta_apply = None

        if self.view is not None:
            self.view.init_from_model()

    def apply_delta(self, delta):
        self._delayed_delta_apply = delta

    def set_chosen(self, choice):
        if not self._connected:
            return
        if self._updating:
            return
        self.chosen = int(choice)
        if len(self.choices) > self.chosen:
            self.set_data(self.choices[self.chosen])

    def update_xml(self):
        self.xml.attrib["chosen"] = str(self.chosen)

    def decommission(self):
        if self._registered:
            self.get_root().unregister_callback(
                self._collection_path,
                self._update_choices,
                self._collection_path.count("."),
            )
            self._registered = False
        for path in self._registered_paths:
            self._root.unregister_callback(
                path, self._update_choices, self.path_depth()
            )
        self._registered_paths.clear()

        super().decommission()

    def get_secure_schema(self) -> Optional[str]:
        schema = {self.name: {"type": "string"}}
        return schema


class WaNoMatrixModel(AbstractWanoModel):
    def __init__(self, *args, **kwargs):
        super(WaNoMatrixModel, self).__init__(*args, **kwargs)

        self.rows = 0
        self.cols = 0
        self.col_header = None
        self.row_header = None
        self.storage = None
        self._default = None

    def parse_from_xml(self, xml):
        super().parse_from_xml(xml)
        self.xml = xml

        self.rows = int(self.xml.attrib["rows"])
        self.cols = int(self.xml.attrib["cols"])
        self.col_header = None
        if "col_header" in self.xml.attrib:
            self.col_header = self.xml.attrib["col_header"].split(";")
        self.row_header = None
        if "row_header" in self.xml.attrib:
            self.row_header = self.xml.attrib["row_header"].split(";")

        if self.xml.text is None or self.xml.text.strip() == "":
            self.storage = [[] for i in range(self.rows)]
            for i in range(self.rows):
                self.storage[i] = []
                for j in range(self.cols):
                    self.storage[i].append("")
        else:
            self.storage = self._fromstring(self.xml.text)
        self._default = copy.deepcopy(self.storage)

    def _tostring(self, ar):
        returnstring = "[ "
        for row in ar:
            returnstring += "[ "
            for val in row[:-1]:
                myval = self._add_explicit_quotes_if_string(val)
                returnstring += f" {myval} ,"
            myval = self._add_explicit_quotes_if_string(row[-1])
            returnstring += f" {myval} ] , "
        returnstring = returnstring[:-3]
        returnstring += " ] "
        return returnstring

    def _add_explicit_quotes_if_string(self, value):
        try:
            a = float(value)
            return a
        except ValueError:
            return f'"{value}"'

    def get_delta_to_default(self):
        return self._tostring(self.storage)

    def apply_delta(self, delta):
        self.storage = self._fromstring(delta)

    def changed_from_default(self) -> bool:
        return np.any(np.asarray(self.storage) != np.asarray(self._default))

    def _cast_to_correct_type(self, value):
        try:
            a = float(value)
            return a
        except ValueError:
            return str(value)

    def set_data(self, i, j, data):
        self.storage[i][j] = self._cast_to_correct_type(data)

    def _fromstring(self, stri):
        stri = stri.strip()
        list_of_lists = ast.literal_eval(stri)
        if not isinstance(list_of_lists, list):
            raise SyntaxError("Expected list of lists")
        for i in range(len(list_of_lists)):
            for j in range(len(list_of_lists[i])):
                list_of_lists[i][j] = self._cast_to_correct_type(list_of_lists[i][j])
        return list_of_lists

    def __getitem__(self, item):
        return self._tostring(self.storage)

    def get_type_str(self):
        return None

    def get_data(self):
        return self._tostring(self.storage)

    def update_xml(self):
        self.xml.text = self._tostring(self.storage)

    def get_secure_schema(self) -> Optional[str]:
        schema = {self.name: {"type": "string", "pattern": r"\[\s*\[.+\]\s*\]"}}
        # schema = {
        #     self.name : {
        #         "type": "array",
        #         "items": {
        #             "type": "array",
        #             "items": {
        #                 "anyOf": [
        #                     { "type": "number"},
        #                     { "type": "string"},
        #                     {"type": "integer"},
        #                     {"type": "null"},
        #                 ],
        #             },
        #         }
        #     }
        # }
        return schema


class WaNoModelListLike(AbstractWanoModel):
    def __init__(self, *args, **kwargs):
        super(WaNoModelListLike, self).__init__(*args, **kwargs)
        self.wano_list = []
        self.style = ""

    def parse_from_xml(self, xml):
        self.xml = xml

        if "style" in self.xml.attrib:
            self.style = self.xml.attrib["style"]
        else:
            self.style = ""
        for current_id, child in enumerate(self.xml):
            if not is_regular_element(child):
                continue
            ModelClass = SimStackServer.WaNo.WaNoFactory.WaNoFactory.get_model_class(
                child.tag
            )
            ViewClass = SimStackServer.WaNo.WaNoFactory.WaNoFactory.get_qt_view_class(
                child.tag
            )
            model = ModelClass()
            model.set_view_class(ViewClass)
            model.parse_from_xml(child)
            self.wano_list.append(model)

    @property
    def listlike(self):
        return True

    def __len__(self):
        return len(self.wano_list)

    def __getitem__(self, item):
        item = int(item)
        return self.wano_list[item]

    def get_type_str(self):
        return None

    def items(self):
        return enumerate(self.wano_list)

    def wanos(self):
        return enumerate(self.wano_list)

    def set_parent_visible(self, is_visible):
        super().set_parent_visible(is_visible)
        if self._isvisible:
            for model in self.wano_list:
                model.set_parent_visible(is_visible)

    def changed_from_default(self) -> bool:
        return False

    def set_visible(self, is_visible):
        super().set_visible(is_visible)
        for model in self.wano_list:
            model.set_parent_visible(is_visible)

    def update_xml(self):
        for wano in self.wano_list:
            wano.update_xml()

    def decommission(self):
        for wano in self.wano_list:
            wano.decommission()
        super().decommission()

    def get_secure_schema(self) -> Optional[str]:
        raise NotImplementedError(
            "WaNo Secure Schema not supported on pure WaNoModelListLike"
        )


class WaNoNoneModel(AbstractWanoModel):
    def __init__(self, *args, **kwargs):
        super(WaNoNoneModel, self).__init__(*args, **kwargs)

    def parse_from_xml(self, xml):
        self.xml = xml
        super().parse_from_xml(xml)

    def get_data(self):
        return ""

    def set_data(self, data):
        ""
        pass

    def __getitem__(self, item):
        return None

    def get_type_str(self):
        return "String"

    def update_xml(self):
        pass

    def changed_from_default(self) -> bool:
        return False

    def __repr__(self):
        return ""

    def get_secure_schema(self) -> Optional[str]:
        schema = {
            self.name: {
                "type": "string",
            }
        }
        return schema


class WaNoSwitchModel(WaNoModelListLike):
    def __init__(self, *args, **kwargs):
        super(WaNoSwitchModel, self).__init__(*args, **kwargs)
        self._switch_name_list = []
        self._names_list = []
        self._switch_path = None
        self._visible_thing = -1
        self._registered = False
        # self._name = "unset"

    def parse_from_xml(self, xml):
        super().parse_from_xml(xml)
        self.xml = xml
        for child in self.xml:
            if not is_regular_element(child):
                continue
            switch_name = child.attrib["switch_name"]
            name = child.attrib["name"]
            self._names_list.append(name)
            self._switch_name_list.append(switch_name)
        self._parse_switch_conditions(self.xml)
        self._visible_thing = -1
        self._name = self._names_list[self._visible_thing]

    @property
    def listlike(self):
        return True

    @property
    def dictlike(self):
        return False

    # def __getitem__(self, item):
    #    return self.wano_list[self._visible_thing].__getitem__(item)
    # ToDo in usage?
    def __iter__(self):
        return self.wano_list.__iter__()

    def items(self):
        return enumerate(self.wano_list)

    def __reversed__(self):
        return self.wano_list.__reversed__()

    def get_delta_to_default(self):
        return self._visible_thing

    def apply_delta(self, delta):
        self._visible_thing = delta
        self._name = self._names_list[self._visible_thing]
        if self._view is not None:
            self._view.init_from_model()

    def changed_from_default(self) -> bool:
        # We always have to remember which switch condition was active
        return True

    def get_selected_id(self):
        if self._visible_thing >= 0:
            return self._visible_thing
        else:
            return 0

    def _evaluate_switch_condition(self, changed_path):
        if changed_path != self._switch_path and not changed_path == "force":
            return
        # print("Evaluating mypath %s for changed_path %s"%(self._switch_path, changed_path))
        visible_thing_string = self._root.get_value(self._switch_path).get_data()
        try:
            visible_thing = self._switch_name_list.index(visible_thing_string)
            self._visible_thing = visible_thing
            self._name = self._names_list[self._visible_thing]
            if self._view is not None:
                self._view.init_from_model()
        except (IndexError, KeyError) as e:
            print("This will throw!", e)
            pass

    def get_type_str(self):
        if self._visible_thing >= 0:
            # print(self._visible_thing, self.wano_list, self._name, self.path)
            return self.wano_list[self._visible_thing].get_type_str()
        return "unset"

    def get_data(self):
        if self._visible_thing >= 0:
            return self.wano_list[self._visible_thing].get_data()
        return "unset"

    def set_path(self, path):
        super().set_path(path)
        self._switch_path = Template(self._switch_path).render(
            path=self._path.split(".")
        )
        if not self._registered:
            self._root.register_callback(
                self._switch_path, self._evaluate_switch_condition, self.path_depth()
            )
            self._registered = True

    # ToDo: Timo this does not have any usage except in the test?
    def get_parent(self):
        return self._parent

    def set_parent(self, parent):
        super().set_parent(parent)

    def set_root(self, root):
        super().set_root(root)

    def _parse_switch_conditions(self, xml):
        self._switch_path = xml.attrib["switch_path"]

    def decommission(self):
        self._root.unregister_callback(
            self._switch_path, self._evaluate_switch_condition, self.path_depth()
        )
        self._registered = False
        for wano in self.wano_list:
            wano.decommission()
        super().decommission()

    def get_secure_schema(self) -> Optional[str]:
        child_schemata = []
        for child in self.wano_list:
            if isinstance(child, WaNoSwitchModel):
                raise NotImplementedError(
                    "A switch model cannot be directly inside a switch model."
                )
            child_schemata.append(child.get_secure_schema())
        schema = {
            "oneOf": child_schemata,
        }
        return schema


class MultipleOfModel(AbstractWanoModel):
    def __init__(self, *args, **kwargs):
        super(MultipleOfModel, self).__init__(*args, **kwargs)

        self.first_xml_child = None
        self.list_of_dicts = []
        self._default_len = -1

    def parse_from_xml(self, xml):
        self.xml = xml
        for child in self.xml:
            if not is_regular_element(child):
                continue
            if self.first_xml_child is None:
                self.first_xml_child = child
            wano_temp_dict = self.parse_one_child(child)
            self.list_of_dicts.append(wano_temp_dict)
        super().parse_from_xml(xml)
        self._default_len = len(self.list_of_dicts)

    def numitems_per_add(self):
        return len(self.first_xml_child)

    def set_parent(self, parent):
        super().set_parent(parent)
        for wano_dict in self.list_of_dicts:
            for wano in wano_dict.values():
                wano.set_parent(self)

    @property
    def listlike(self):
        return True

    def get_secure_schema(self) -> Optional[str]:
        first_item = self.list_of_dicts[0]
        required_list = []
        child_properties_dict = {}
        oneOf_property_dict = None
        number_of_switches = 0
        for item_name, item_dict in first_item.items():
            if isinstance(item_dict, WaNoSwitchModel):
                number_of_switches += 1
                if number_of_switches == 2:
                    raise NotImplementedError(
                        "Only one WaNoSwitch allowed per MultipleOf"
                    )
                oneOf_property_dict = item_dict.get_secure_schema()
                continue
            required_list.append(item_name)
            child_properties_dict.update(item_dict.get_secure_schema())
        schema = {
            "type": "array",
            "items": {
                "type": "object",
                "properties": child_properties_dict,
                "additionalProperties": False,
            },
            "required": required_list,
        }
        if oneOf_property_dict is not None:
            schema["items"].update(oneOf_property_dict)

        return {self.name: schema}

    def number_of_multiples(self):
        return len(self.list_of_dicts)

    def last_item_check(self):
        return len(self.list_of_dicts) == 1

    # ToDo: Timo - should be private?
    def parse_one_child(self, child, build_view=False):
        # A bug still exists, which allows visibility conditions to be fired prior to the existence of the model
        # but this is transient.
        wano_temp_dict = OrderedDictIterHelper()
        current_id = len(self.list_of_dicts)
        # fp = "%s.%d"%(self.full_path,current_id)
        for cchild in child:
            ModelClass = SimStackServer.WaNo.WaNoFactory.WaNoFactory.get_model_class(
                cchild.tag
            )
            ViewClass = SimStackServer.WaNo.WaNoFactory.WaNoFactory.get_qt_view_class(
                cchild.tag
            )
            model = ModelClass()
            model.set_view_class(ViewClass)
            model.parse_from_xml(cchild)
            name = cchild.attrib["name"]
            start_path = [*self.path.split(".")] + [str(current_id), model.name]

            model.set_name(name)
            rootview = None
            if build_view:
                self.get_root()
                model.set_root(self.get_root())

                (
                    model,
                    rootview,
                ) = SimStackServer.WaNo.WaNoFactory.wano_constructor_helper(
                    model, start_path=start_path, parent_view=self.view
                )
                rootview.set_parent(self.view)

            model.set_parent(self)
            wano_temp_dict[name] = model
        return wano_temp_dict

    def __getitem__(self, item):
        item = int(item)
        return self.list_of_dicts[item]

    def __iter__(self):
        return iter(self.list_of_dicts)

    def items(self):
        return enumerate(self.list_of_dicts)

    def __reversed__(self):
        return reversed(self.list_of_dicts)

    def get_data(self):
        return self.list_of_dicts

    def get_type_str(self):
        return "MultipleOf"

    def __len__(self):
        return len(self.list_of_dicts)

    def set_data(self, list_of_dicts):
        self.list_of_dicts = list_of_dicts

    def delete_item(self):
        if len(self.list_of_dicts) > 1:
            before = self._root.block_signals(True)
            for wano in self.list_of_dicts[-1].values():
                wano.decommission()
            self.list_of_dicts.pop()
            for child in reversed(self.xml):
                if not is_regular_element(child):
                    continue
                self.xml.remove(child)
                break

            self._root.block_signals(before)
            self._root.datachanged_force()

            return True
        return False

    def add_item(self, build_view=True):
        before = self._root.block_signals(True)
        my_xml = copy.copy(self.first_xml_child)
        my_xml.attrib["id"] = str(len(self.list_of_dicts))
        self.xml.append(my_xml)
        model_dict = self.parse_one_child(my_xml, build_view=build_view)
        self.list_of_dicts.append(model_dict)
        self._root.block_signals(before)
        self.get_root().datachanged_force()
        if self.view is not None:
            self.view.init_from_model()

    def get_delta_to_default(self):
        return len(self.list_of_dicts)

    def apply_delta(self, delta):
        while len(self.list_of_dicts) < delta:
            if self.view is not None:
                self.add_item(build_view=True)
            else:
                self.add_item(build_view=False)
        while len(self.list_of_dicts) > delta:
            self.delete_item()

    def changed_from_default(self) -> bool:
        return len(self.list_of_dicts) != self._default_len

    def set_parent_visible(self, is_visible):
        super().set_parent_visible(is_visible)
        if self._isvisible:
            for wano_dict in self.list_of_dicts:
                for wano in wano_dict.values():
                    wano.set_parent_visible(is_visible)

    def set_visible(self, is_visible):
        super().set_visible(is_visible)
        for wano_dict in self.list_of_dicts:
            for wano in wano_dict.values():
                wano.set_parent_visible(is_visible)

    def update_xml(self):
        for wano_dict in self.list_of_dicts:
            for wano in wano_dict.values():
                wano.update_xml()

    def decommission(self):
        for wano_dict in self.list_of_dicts:
            for wano in wano_dict.values():
                wano.decommission()

        super().decommission()


# This is the parent class and grandfather. Children have to be unique, no lists here
class WaNoModelRoot(WaNoModelDictLike):
    def _exists_read_load(self, object, pathobj: Path):
        if pathobj.exists():
            object.load(pathobj)
        else:
            object.make_default_list()
            # object.save(pathobj)

    def set_parent_wf(self, parent_wf):
        self._parent_wf = parent_wf

    def get_parent_wf(self):
        return self._parent_wf

    def get_render_substitutions(self):
        return self._render_substitutions

    def __init__(self, *args, **kwargs):
        super(WaNoModelRoot, self).__init__(*args, **kwargs)
        self._explicit_xml = kwargs.get("explicit_xml", "unset")
        self._logger = logging.getLogger("WaNoModelRoot")
        self._datachanged_callbacks = {}
        self._outputfile_callbacks = []
        self._notifying = False
        self._unregister_list = []
        self._register_list = []
        self._wano_dir_root = kwargs["wano_dir_root"]
        self._my_export_paths = []
        self._output_schema = None
        self._block_signals = False
        self._render_substitutions = {}

        self._new_resource_model = Resources()

        if "model_only" in kwargs and kwargs["model_only"] is True:
            self.import_model = None
            self.export_model = None
        else:
            from simstack.view.PropertyListView import (
                ImportTableModel,
                ExportTableModel,
            )

            self.import_model = ImportTableModel(parent=None, wano_parent=self)
            self.import_model.make_default_list()

            self.export_model = ExportTableModel(parent=None, wano_parent=self)
            self.export_model.make_default_list()
            self._read_export(self._wano_dir_root)

        self._read_output_schema(self._wano_dir_root)

        self._root = self

        self.rendered_exec_command = ""

        self.input_files = []
        self.output_files = []

        self.metas = OrderedDictIterHelper()
        self._parse_defaults()

    def get_secure_schema(self) -> Dict[str, Any]:
        child_properties = super().get_secure_schema()
        # WaNoModelRoot has to filter one level and TABS due to the super call
        child_properties = child_properties[self.name]["properties"]
        baseline_schema = {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": "https://example.com/product.schema.json",
            "title": self.name,
            "description": f"{self.name} secure schema",
            "type": "object",
            "properties": child_properties,
            "required": [*child_properties.keys()],
            "additionalProperties": False,
        }
        return baseline_schema

    def verify_against_secure_schema(self, verification_dict: Dict[str, Any]):
        # Will raise in case of error
        jsonschema.validate(verification_dict, self.get_secure_schema())

    def get_new_resource_model(self) -> Resources:
        return self._new_resource_model

    def block_signals(self, true_or_false):
        before = self._block_signals
        self._block_signals = true_or_false
        return before

    def _read_export(self, directory: pathlib.Path):
        # We want to allow construction without QT view imports, which are happening here
        if self.import_model:
            imports_fn = directory / "imports.yml"
            self._exists_read_load(self.import_model, imports_fn)

        if self.export_model:
            exports_fn = directory / "exports.yml"
            self._exists_read_load(self.export_model, exports_fn)

        resources_fn = directory / "resources.yml"
        if resources_fn.is_file():
            try:
                self._new_resource_model.from_json(resources_fn)
            except JSONDecodeError:
                resources_fn.unlink()

    def _read_output_schema(self, directory: pathlib.Path):
        output_schema = directory / "output_schema.json"
        if output_schema.is_file():
            self._output_schema = json.loads(output_schema.read_text())

    def verify_output_against_schema(self, content: Dict[str, Any]):
        if not self._output_schema:
            raise ValueError(
                "Could not verify content, because no output schema was found"
            )
        jsonschema.validate(content, self._output_schema)

    @staticmethod
    def _parse_xml(xmlpath: pathlib.Path):
        with xmlpath.open("rt") as infile:
            xml = etree.parse(infile).getroot()
            return xml

    def _parse_defaults(self):
        if self._explicit_xml != "unset":
            xmlpath = Path(self._explicit_xml)
        else:
            wle = WaNoListEntry_from_folder_or_zip(self._wano_dir_root)
            xmlpath = get_wano_xml_path(
                self._wano_dir_root, wano_name_override=wle.name
            )
        xml = self._parse_xml(xmlpath)
        self._parse_from_xml(xml)

    def parse_from_xml(self, xml):
        print("Fake Call")

    def _parse_from_xml(self, xml):
        self.full_xml = xml
        subxml = self.full_xml.find("WaNoRoot")
        export_dictionaries = {}
        for child in self.full_xml.findall("./WaNoOutputFiles/WaNoOutputFile"):
            self.output_files.append(child.text)
            if child.text == "output_config.ini":
                absfile = join(self._wano_dir_root, "output_config.ini")
                if os.path.isfile(absfile):
                    export_dictionaries["ini"] = absfile

            elif child.text == "output_dict.yml":
                absfile = join(self._wano_dir_root, "output_dict.yml")
                if os.path.isfile(absfile):
                    export_dictionaries["dict"] = absfile

        if len(export_dictionaries) > 0:
            rr = ReportRenderer(export_dictionaries)
            my_exports = rr.consolidate_export_dictionaries()
            self._my_export_paths = [*flatten_dict(my_exports).keys()]

        for child in self.full_xml.findall("./WaNoInputFiles/WaNoInputFile"):
            self.input_files.append((child.attrib["logical_filename"], child.text))

        el = self.full_xml.find("./WaNoMeta")
        if el is not None:
            self.metas = xmltodict.parse(etree.tostring(el))

        self.exec_command = self.full_xml.find("WaNoExecCommand").text
        for child in self.full_xml.find("WaNoExecCommand"):
            raise WaNoParseError(
                "Another XML element was found in WaNoExecCommand. (This can be comments or open and close tags). This is not supported. Aborting Parse."
            )

        super().parse_from_xml(xml=subxml)

    def _tidy_lists(self):
        while len(self._unregister_list) > 0:
            key, func, depth = self._unregister_list.pop()
            self.unregister_callback(key, func, depth)

        while len(self._register_list) > 0:
            key, func, depth = self._register_list.pop()
            self.register_callback(key, func, depth)

    def notify_datachanged(self, path):
        if self._block_signals:
            return
        if self._notifying:
            return

        self._tidy_lists()

        # print("Checking changed path %s"%path)
        if "unset" in path:
            print("Found unset in path %s" % path)
        self._notifying = True
        if path == "force":
            toeval_by_prio = {}
            for callback_prio_dict in self._datachanged_callbacks.values():
                for callback_prio in reversed(callback_prio_dict):
                    if callback_prio not in toeval_by_prio:
                        toeval_by_prio[callback_prio] = []
                    for callback in callback_prio_dict[callback_prio]:
                        toeval_by_prio[callback_prio].append(callback)
                        # callback(path)
            for callback_prio in reversed(toeval_by_prio):
                for callback in toeval_by_prio[callback_prio]:
                    callback(path)

        if path in self._datachanged_callbacks:
            callback_prio_dict = self._datachanged_callbacks[path]
            for callback_prio in reversed(callback_prio_dict):
                for callback in callback_prio_dict[callback_prio]:
                    callback(path)
        self._notifying = False

        self._tidy_lists()

    def register_callback(self, path, callback_function, depth):
        if self._notifying:
            toregister = (path, callback_function, depth)
            if toregister not in self._register_list:
                self._register_list.append(toregister)
        else:
            if path not in self._datachanged_callbacks:
                self._datachanged_callbacks[path] = {}
            if depth not in self._datachanged_callbacks[path]:
                self._datachanged_callbacks[path][depth] = []

            if callback_function not in self._datachanged_callbacks[path][depth]:
                # print(f"Registering callback for {path} with {depth}, function was: {callback_function.__self__.path}.")
                self._datachanged_callbacks[path][depth].append(callback_function)

    def unregister_callback(self, path, callback_function, depth):
        assert (
            path in self._datachanged_callbacks
        ), "When unregistering a function, it has to exist in datachanged_callbacks."
        # print(f"Unregistering callback for {path} with {depth}. function was: {callback_function.__self__.path}.")
        assert (
            callback_function in self._datachanged_callbacks[path][depth]
        ), f"Unregistering callback for {path} with {depth} failed, function was: {callback_function.__self__.path}. Function not found in callbacks."
        # print("Removing %s for %s"%(path, callback_function))
        if self._notifying:
            self._unregister_list.append((path, callback_function, depth))
        else:
            self._datachanged_callbacks[path][depth].remove(callback_function)

    def get_type_str(self):
        return "WaNoRoot"

    def get_import_model(self):
        return self.import_model

    def get_export_model(self):
        return self.export_model

    def register_outputfile_callback(self, function):
        self._outputfile_callbacks.append(function)

    def get_output_files(self, only_static=False):
        return_files = []

        rendered_wano = None
        for outputfile in self.output_files:
            if "{{" in outputfile and "}}" in outputfile:
                if rendered_wano is None:
                    rendered_wano = self.wano_walker()
                outfile = Template(outputfile, newline_sequence="\n").render(
                    wano=rendered_wano
                )
                return_files.append(outfile)
            else:
                return_files.append(outputfile)

        if only_static:
            return return_files

        return_files = return_files + [a[0] for a in self.export_model.get_contents()]
        for callback in self._outputfile_callbacks:
            return_files += callback()
        return return_files

    def datachanged_force(self):
        self.notify_datachanged("force")

    def save_xml(self, wano: WaNoListEntry):
        raise NotImplementedError("Saving the XML is not supported anymore.")

    def get_changed_command_paths(self):
        """These are paths, which require a WaNoElement to be changed, which is dynamic, such as multipleof or switch"""
        tw = WaNoTreeWalker(self)

        changed_paths = {}

        def dict_change_detector(subdict, call_info):
            twp = call_info["nestdictmod_paths"].abspath
            if (
                hasattr(subdict, "changed_from_default")
                and subdict.changed_from_default()
            ):
                changed_paths[
                    ".".join(str(e) for e in twp)
                ] = subdict.get_delta_to_default()
            return None

        tw.walker(
            capture=False,
            path_visitor_function=None,
            subdict_visitor_function=dict_change_detector,
            data_visitor_function=None,
        )
        return changed_paths

    def get_changed_paths(self):
        tw = WaNoTreeWalker(self)

        def leafnode_change_detector(leaf_node: AbstractWanoModel, call_info):
            if leaf_node.changed_from_default():
                return leaf_node.get_delta_to_default()
            else:
                # We only wanto to collect changed paths
                raise EraseEntryError()

        changed_paths_no_dict = tw.walker(
            capture=True,
            path_visitor_function=None,
            subdict_visitor_function=None,
            data_visitor_function=leafnode_change_detector,
        )

        def empty_dict_remover(subdict, call_info):
            relpath = call_info["nestdictmod_paths"].relpath

            # We should not do anything which entries which were lists before to protect multipleof:
            if isinstance(relpath, int) or relpath.isdigit():
                return None

            if isinstance(subdict, MultipleOfModel):
                # We can never remove a path to a multiple of model
                return None
            if len(subdict) == 0:
                raise EraseEntryError()

            return None

        # We clean up this dictionary five times. A smarter way would be to implement a subdict_visitor_function
        # in WaNoTreeWalker, which runs subdict_visitorafter collecting
        try:
            for i in range(0, 5):
                dict_remove_tw = NestDictMod(changed_paths_no_dict)
                changed_paths_no_dict = dict_remove_tw.walker(
                    capture=True,
                    path_visitor_function=None,
                    subdict_visitor_function=empty_dict_remover,
                    data_visitor_function=None,
                )
        except EraseEntryError:
            # In case an EraseEntryError was thrown on the highest level (i.e no changes at all)
            changed_paths_no_dict = {}
        return changed_paths_no_dict

    def save_resources_and_imports(self, outfolder: Path):
        resources_fn = outfolder / "resources.yml"
        self._new_resource_model.to_json(resources_fn)

        imports_fn = outfolder / "imports.yml"
        self.import_model.save(imports_fn)

        exports_fn = outfolder / "exports.yml"
        self.export_model.save(exports_fn)

    def save(self, outfolder):
        delta_json = Path(outfolder) / "wano_configuration.json"
        self.save_delta_json(delta_json)
        self.save_resources_and_imports(Path(outfolder))

    def read_from_wano_delta(self, wd: WaNoDelta, infolder: pathlib.Path):
        self.apply_delta_dict(wd.command_dict)
        self.apply_delta_dict(wd.value_dict)
        self._read_export(infolder)
        self.datachanged_force()

    def read(self, infolder: pathlib.Path):
        wd = WaNoDelta(infolder)
        self.read_from_wano_delta(wd, infolder)

    def set_wano_dir_root(self, wano_dir_root):
        self._wano_dir_root = wano_dir_root

    def get_metadata_dict(self):
        return {
            "name": self.name,
            "folder": self._wano_dir_root.name,
        }

    def save_delta_json(self, savepath):
        outdict = {
            "commands": self.get_changed_command_paths(),
            "values": self.get_changed_paths(),
            "metadata": self.get_metadata_dict(),
        }
        with savepath.open("wt") as outfile:
            json.dump(outdict, outfile, indent=4)
        return True

    def wano_walker_paths(self, parent=None, path="", output=[]):
        if parent is None:
            parent = self

        if isinstance(parent, WaNoSwitchModel):
            parent = parent[parent.get_selected_id()]

        listlike, dictlike = self._listlike_dictlike(parent)
        if listlike:
            for key, wano in parent.items():
                mypath = copy.copy(path)
                if mypath == "":
                    mypath = "%s" % (key)
                else:
                    mypath = "%s.%s" % (mypath, key)
                self.wano_walker_paths(parent=wano, path=mypath, output=output)

        elif dictlike:
            for key, wano in parent.items():
                mypath = copy.copy(path)
                if hasattr(wano, "name"):
                    # Actual dict
                    key = wano.name
                # else list
                if mypath == "":
                    mypath = "%s" % (key)
                else:
                    mypath = "%s.%s" % (mypath, key)
                self.wano_walker_paths(parent=wano, path=mypath, output=output)
        else:
            output.append((path, parent.get_type_str()))
        return output

    def wano_walker(self, parent=None, path=""):
        if parent is None:
            parent = self

        if isinstance(parent, WaNoSwitchModel):
            parent = parent[parent.get_selected_id()]
        # print(type(parent))
        listlike, dictlike = self._listlike_dictlike(parent)
        if listlike:
            my_list = []
            for key, wano in parent.items():
                mypath = copy.copy(path)
                if mypath == "":
                    mypath = "%s" % (key)
                else:
                    mypath = "%s.%s" % (mypath, key)
                my_list.append(self.wano_walker(parent=wano, path=mypath))
            return my_list
        elif dictlike:
            my_dict = {}
            for key, wano in parent.items():
                mypath = copy.copy(path)
                if hasattr(wano, "name"):
                    # Actual dict
                    key = wano.name
                # else list
                if mypath == "":
                    mypath = "%s" % (key)
                else:
                    mypath = "%s.%s" % (mypath, key)
                my_dict[key] = self.wano_walker(parent=wano, path=mypath)
            return my_dict
        else:
            # print("%s %s" % (path, parent.get_data()))
            return parent.get_rendered_wano_data()

    def _listlike_dictlike(self, myobject):
        listlike = False
        dictlike = False
        if isinstance(myobject, collections.OrderedDict) or isinstance(myobject, dict):
            listlike = False
            dictlike = True
        elif isinstance(myobject, list):
            listlike = True
            dictlike = False

        if hasattr(myobject, "listlike"):
            listlike = myobject.listlike
        if hasattr(myobject, "dictlike"):
            dictlike = myobject.dictlike

        return listlike, dictlike

    @classmethod
    def _filename_is_global_var(cls, filename):
        if re.match(r"^\$\{.*\}$", filename) is not None:
            return True
        return False

    def wano_walker_render_pass(
        self,
        rendered_wano,
        parent=None,
        path="",
        submitdir="",
        flat_variable_list=None,
        input_var_db=None,
        output_var_db=None,
        runtime_variables=None,
    ):
        if parent is None:
            parent = self

        if isinstance(parent, WaNoSwitchModel):
            parent = parent[parent.get_selected_id()]
        # print(type(parent))
        """
        import traceback
        parent_type_string = None
        if hasattr(parent,"get_type_str"):
            parent_type_string = parent.get_type_str()
        if parent_type_string is None:
            parent_type_string = "None"
        if parent_type_string == "File":
            print("In path",path,"depth:",path.count(".")+2,parent_type_string)
        """

        listlike, dictlike = self._listlike_dictlike(parent)
        if listlike:
            my_list = []
            for key, wano in parent.items():
                mypath = copy.copy(path)
                if mypath == "":
                    mypath = "%s" % (key)
                else:
                    mypath = "%s.%s" % (mypath, key)
                my_list.append(
                    self.wano_walker_render_pass(
                        rendered_wano,
                        parent=wano,
                        path=mypath,
                        submitdir=submitdir,
                        flat_variable_list=flat_variable_list,
                        input_var_db=input_var_db,
                        output_var_db=output_var_db,
                        runtime_variables=runtime_variables,
                    )
                )
            return my_list
        elif dictlike:
            my_dict = {}
            for key, wano in parent.items():
                mypath = copy.copy(path)
                if hasattr(wano, "name"):
                    # Actual dict
                    key = wano.name
                # else list
                if mypath == "":
                    mypath = "%s" % (key)
                else:
                    mypath = "%s.%s" % (mypath, key)
                my_dict[key] = self.wano_walker_render_pass(
                    rendered_wano,
                    parent=wano,
                    path=mypath,
                    submitdir=submitdir,
                    flat_variable_list=flat_variable_list,
                    input_var_db=input_var_db,
                    output_var_db=output_var_db,
                    runtime_variables=runtime_variables,
                )
            return my_dict
        else:
            # We should avoid merging and splitting. It's useless, we only need splitpath anyways
            splitpath = path.split(".")
            # path is complete here, return path
            rendered_parent = parent.render(
                rendered_wano, splitpath, submitdir=submitdir
            )
            if (
                isinstance(rendered_parent, str)
                and input_var_db is not None
                and output_var_db is not None
            ):
                if rendered_parent.startswith("${") and rendered_parent.endswith("}"):
                    varname = rendered_parent[2:-1]

                    if runtime_variables is not None:
                        for (
                            runtime_varname,
                            runtime_varvalue,
                        ) in runtime_variables.items():
                            varname = varname.replace(runtime_varname, runtime_varvalue)
                            rendered_parent = varname

                    if varname in input_var_db:
                        self._render_substitutions[path] = varname
                        rendered_parent = input_var_db[varname]
                    if varname in output_var_db:
                        self._render_substitutions[path] = varname
                        rendered_parent = output_var_db[varname]

            if flat_variable_list is not None:
                rendered_parent_jsdl = rendered_parent
                if parent.get_type_str() == "File":
                    filename = parent.get_data()
                    if parent.get_local():
                        pass
                        # to_upload = os.path.join(submitdir, "workflow_data")
                        # cp = os.path.commonprefix([to_upload, filename])
                        # relpath = os.path.relpath(filename, cp)
                        # print("relpath was: %s"%relpath)
                        # filename= "c9m:${WORKFLOW_ID}/%s" % relpath
                        # filename = "BFT:${STORAGE_ID}/%s" % relpath
                        # filename = os.path.join("inputs",relpath)
                        # Absolute filenames will be replace with BFT:STORAGEID etc. below.
                    elif not self._filename_is_global_var(filename):
                        if "outputs/" in filename:
                            # Newer handling, not rewriting filename, because it's already taken care of
                            filename = "c9m:${STORAGE}/workflow_data/%s" % (filename)
                        else:
                            last_slash = filename.rfind("/")
                            first_part = filename[0:last_slash]
                            second_part = filename[last_slash + 1 :]
                            # We cut this here to add the outputs folder. This is a bit hacky - we should differentiate between display name and
                            # name on cluster
                            filename = "c9m:${STORAGE}/workflow_data/%s/outputs/%s" % (
                                first_part,
                                second_part,
                            )

                    rendered_parent_jsdl = (rendered_parent, filename)

                flat_variable_list.append(
                    (path, parent.get_type_str(), rendered_parent_jsdl)
                )
            return rendered_parent

    def prepare_files_submission(self, rendered_wano, basefolder):
        basefolder = os.path.join(basefolder, "inputs")
        mkdir_p(basefolder)
        raw_xml = os.path.join(basefolder, self._name + ".xml")
        with open(raw_xml, "wt") as outfile:
            outfile.write(etree.tounicode(self.full_xml, pretty_print=True))

        self.save(Path(basefolder))

        for remote_file, local_file in self.input_files:
            comp_filename = os.path.join(self._wano_dir_root, local_file)
            comp_filename = os.path.abspath(comp_filename)
            comp_dir = os.path.dirname(comp_filename)
            comp_basename = os.path.basename(comp_filename)

            joined_filename = os.path.join(comp_dir, comp_basename)

            if not os.path.exists(os.path.join(joined_filename)):
                print(
                    "File <%s> not found on disk, please check for spaces before or after the filename."
                    % comp_filename
                )
                raise FileNotFoundErrorSimStack(
                    "File <%s> not found on disk, please check for spaces before or after the filename."
                    % comp_filename
                )

            outfile = os.path.join(basefolder, local_file)
            dirn = os.path.dirname(outfile)
            mkdir_p(dirn)
            print(
                f"Copying from {comp_filename} to {dirn}. Remote filename was {remote_file}"
            )
            shutil.copy(comp_filename, dirn)

    def flat_variable_list_to_jsdl(self, fvl, basedir, stageout_basedir):
        local_stagein_files = []
        runtime_stagein_files = []
        runtime_stageout_files = []

        for myid, (logical_filename, source) in enumerate(self.input_files):
            fvl.append(("IFILE%d" % (myid), "File", (logical_filename, source)))
            # local_stagein_files.append([logical_filename,source])

        for varname, type, var in fvl:
            if type == "File":
                log_path_on_cluster = var[1].replace("\\", "/")
                if var[1].startswith("c9m:"):
                    runtime_stagein_files.append([var[0], log_path_on_cluster])
                elif self._filename_is_global_var(var[1]):
                    runtime_stagein_files.append([var[0], log_path_on_cluster])
                else:
                    if isabs(var[1]):
                        # In this case this will be a local import.
                        runtime_stagein_files.append(
                            [
                                var[0],
                                "${STORAGE}/workflow_data/%s/inputs/%s"
                                % (stageout_basedir, var[0]),
                            ]
                        )
                    else:
                        runtime_stagein_files.append(
                            [
                                var[0],
                                "${STORAGE}/workflow_data/%s/inputs/%s"
                                % (stageout_basedir, var[1]),
                            ]
                        )
                    # print(runtime_stagein_files,var)
            else:
                # These should be NON posix arguments in the end
                varname.replace(".", "_")
        # xmlfile = self._name + ".xml"
        # runtime_stagein_files.append([self._name + ".xml","${STORAGE}/workflow_data/%s/inputs/%s" % (stageout_basedir, "rendered_wano.yml)])

        for otherfiles in self.get_import_model().get_contents():
            name, importloc, tostage = otherfiles[0], otherfiles[1], otherfiles[2]
            if self._filename_is_global_var(importloc):
                runtime_stagein_files.append([name, importloc])
            else:
                if "outputs/" in importloc:
                    # New handling, explicit outputs in filename
                    filename = "${STORAGE}/workflow_data/%s" % importloc
                else:
                    # The old handling is broken for subfolders.
                    # Old workflows will run still.
                    # We cut this here to add the outputs folder. This is a bit hacky - we should differentiate between display name and
                    # name on cluster
                    last_slash = importloc.rfind("/")
                    first_part = importloc[0:last_slash]
                    second_part = importloc[last_slash + 1 :]
                    filename = "${STORAGE}/workflow_data/%s/outputs/%s" % (
                        first_part,
                        second_part,
                    )

                # print("In runtime stagein %s"%filename)
                runtime_stagein_files.append([tostage, filename])

        # for filename in self.output_files + [ a[0] for a in self.export_model.get_contents() ]:
        for filename in self.get_output_files(only_static=False):
            # runtime_stageout_files.append([filename,"${STORAGE}/workflow_data/%s/outputs/%s"%(stageout_basedir,filename)])
            runtime_stageout_files.append([filename, filename])

        _runtime_stagein_files = []
        for ft in runtime_stagein_files:
            _runtime_stagein_files.append(["StringList", StringList(ft)])
        runtime_stagein_files = _runtime_stagein_files

        _runtime_stageout_files = []
        for ft in runtime_stageout_files:
            _runtime_stageout_files.append(["StringList", StringList(ft)])
        runtime_stageout_files = _runtime_stageout_files

        """
        _local_stagein_files = []
        for ft in local_stagein_files:
            _local_stagein_files.append(["StringList",StringList(ft)])
        local_stagein_files = _local_stagein_files
        """

        wem = WorkflowExecModule(
            given_name=self.name,
            resources=self.get_new_resource_model(),
            inputs=WorkflowElementList(
                runtime_stagein_files
            ),  # + local_stagein_files),
            outputs=WorkflowElementList(runtime_stageout_files),
            exec_command=self.rendered_exec_command,
        )

        return None, wem, local_stagein_files
        # print(etree.tostring(job_desc, pretty_print=True).decode("utf-8"))

    def render_wano(self, submitdir, stageout_basedir=""):
        # We do two render passes in case values depend on each other
        rendered_wano = self.wano_walker()
        # We do two render passes, in case the rendering reset some values:
        fvl = []
        rendered_wano = self.wano_walker_render_pass(
            rendered_wano, submitdir=submitdir, flat_variable_list=fvl
        )
        # self.rendered_exec_command = Template(self.exec_command,newline_sequence='\n').render(wano = rendered_wano)
        # self.rendered_exec_command = self.rendered_exec_command.strip(' \t\n\r')
        self.rendered_exec_command = self.exec_command
        jsdl, wem, local_stagein_files = self.flat_variable_list_to_jsdl(
            fvl, submitdir, stageout_basedir
        )
        return rendered_wano, jsdl, wem, local_stagein_files

    def render_exec_command(self, rendered_wano):
        rendered_exec_command = Template(
            self.exec_command, newline_sequence="\n"
        ).render(wano=rendered_wano)
        rendered_exec_command = rendered_exec_command.strip(" \t\n\r")
        return rendered_exec_command + "\n"

    # @trace_to_logger
    def render_and_write_input_files(self, basefolder, stageout_basedir=""):
        rendered_wano, jsdl, wem, local_stagein_files = self.render_wano(
            basefolder, stageout_basedir
        )
        self.prepare_files_submission(rendered_wano, basefolder)
        return jsdl

    def render_and_write_input_files_newmodel(self, basefolder, stageout_basedir=""):
        rendered_wano, jsdl, wem, local_stagein_files = self.render_wano(
            basefolder, stageout_basedir
        )
        # pprint(local_stagein_files)
        self.prepare_files_submission(rendered_wano, basefolder)
        return jsdl, wem

    def get_value(self, uri):
        split_uri = uri.split(".")
        current = self.__getitem__(split_uri[0])
        for item in split_uri[1:]:
            current = current[item]
        return current

    def get_all_variable_paths(self, export=True):
        outdict = {}
        self.model_to_dict(outdict)
        tw = NestDictMod(outdict)
        skipdict = tw.walker(
            capture=True,
            path_visitor_function=None,
            subdict_visitor_function=subdict_skiplevel,
            data_visitor_function=None,
        )
        tw = NestDictMod(skipdict)
        pc = PathCollector()
        tw.walker(
            capture=False,
            path_visitor_function=pc.assemble_paths,
            subdict_visitor_function=None,
            data_visitor_function=None,
        )

        if export:
            return pc.paths + self._my_export_paths
        else:
            return pc.paths

    def _get_paths_and_something_helper(
        self, subdict_visitor, deref_functor_path_collector
    ):
        outdict = {}
        self.model_to_dict(outdict)
        tw = NestDictMod(outdict)
        skipdict = tw.walker(
            capture=True,
            path_visitor_function=None,
            subdict_visitor_function=subdict_visitor,
            data_visitor_function=None,
        )
        tw = NestDictMod(skipdict)
        pc = PathCollector()
        tw.walker(
            capture=False,
            path_visitor_function=None,
            subdict_visitor_function=subdict_visitor,
            data_visitor_function=deref_functor_path_collector(pc),
        )
        return pc.path_to_value

    def update_views_from_models(self):
        tw = WaNoTreeWalker(self)

        def init_from_model_visitor(value):
            if hasattr(value, "view"):
                if value.view is not None:
                    value.view.init_from_model()
            return value

        def init_from_model_visitor_subdict(subdict):
            # Subdicts dont require their view rebuilt
            # init_from_model_visitor(subdict)
            return None

        tw.walker(
            capture=False,
            path_visitor_function=None,
            data_visitor_function=init_from_model_visitor,
            subdict_visitor_function=init_from_model_visitor_subdict,
        )

    def get_paths_and_data_dict(self):
        return self._get_paths_and_something_helper(
            subdict_skiplevel, lambda x: x.assemble_paths_and_values
        )

    def get_extra_inputs_aiida(self):
        outfiles = [ftuple[0] for ftuple in self.input_files]
        return outfiles

    def get_paths_and_type_dict_aiida(self):
        outdict = {}
        self.model_to_dict(outdict)
        outdict = tree_list_to_dict_multiply(outdict)
        tw = NestDictMod(outdict)
        skipdict = tw.walker(
            capture=True,
            path_visitor_function=None,
            subdict_visitor_function=subdict_skiplevel_to_type,
            data_visitor_function=None,
        )
        tw = NestDictMod(skipdict)
        pc = PathCollector()
        tw.walker(
            capture=False,
            path_visitor_function=None,
            subdict_visitor_function=subdict_skiplevel_to_type,
            data_visitor_function=pc.assemble_paths_and_values,
        )
        return pc.path_to_value

    def get_valuedict_with_aiida_types(
        self, aiida_files_by_relpath=None, aiida_vars_by_relpath=None
    ):
        if aiida_files_by_relpath is None:
            aiida_files_by_relpath = {}
        outdict = {}
        self.model_to_dict(outdict)
        outdict = tree_list_to_dict(outdict)
        tw = NestDictMod(outdict)
        svf = partial(
            subdict_skiplevel_to_aiida_type,
            aiida_files_by_relpath=aiida_files_by_relpath,
        )
        skipdict = tw.walker(
            capture=True,
            path_visitor_function=None,
            subdict_visitor_function=svf,
            data_visitor_function=None,
        )
        return skipdict

    def get_dir_root(self):
        return self._wano_dir_root

    def apply_delta_dict(self, delta_dict):
        flat_delta_dict = flatten_dict(delta_dict)
        for key, value in flat_delta_dict.items():
            wano_sub: AbstractWanoModel = self.get_value(key)
            wano_sub.apply_delta(value)


class WaNoItemFloatModel(AbstractWanoModel):
    def __init__(self, *args, **kwargs):
        super(WaNoItemFloatModel, self).__init__(*args, **kwargs)
        self._default = -100.0
        self._myfloat = self._default
        self.xml = None

    def parse_from_xml(self, xml):
        self._default = float(xml.text)
        self._myfloat = self._default
        self.xml = xml
        super().parse_from_xml(xml)

    def get_data(self):
        return self._myfloat

    def set_data(self, data):
        self._myfloat = float(data)
        super(WaNoItemFloatModel, self).set_data(data)

    def get_delta_to_default(self):
        import_delta = self._get_import_delta()
        if import_delta:
            return import_delta
        return self.get_data()

    def get_secure_schema(self) -> Optional[str]:
        schema = {self.name: {"type": "number"}}
        return schema

    def apply_delta(self, delta):
        if not self._apply_import_delta(delta):
            self.set_data(delta)

    def __getitem__(self, item):
        return None

    def changed_from_default(self) -> bool:
        if self.do_import:
            return True
        if self._myfloat != self._default:
            return True
        return False

    def get_type_str(self):
        return "Float"

    def update_xml(self):
        super().update_xml()
        if self.xml is not None:
            print(self._myfloat)
            self.xml.text = str(self._myfloat)

    def model_to_dict(self, outdict):
        outdict["data"] = str(self._myfloat)
        super().model_to_dict(outdict)

    def __repr__(self):
        return repr(self._myfloat)


class WaNoItemIntModel(AbstractWanoModel):
    def __init__(self, *args, **kwargs):
        super(WaNoItemIntModel, self).__init__(*args, **kwargs)
        self.myint = -10000000
        self._default = self.myint
        self.xml = None

    def parse_from_xml(self, xml):
        self.myint = float(xml.text)
        self._default = self.myint
        self.xml = xml
        super().parse_from_xml(xml)

    def get_data(self):
        return int(self.myint)

    def get_secure_schema(self) -> Optional[str]:
        schema = {self.name: {"type": "number"}}
        return schema

    def set_data(self, data):
        self.myint = int(data)
        super(WaNoItemIntModel, self).set_data(data)

    def __getitem__(self, item):
        return None

    def get_delta_to_default(self):
        import_delta = self._get_import_delta()
        if import_delta:
            return import_delta
        return self.myint

    def apply_delta(self, delta):
        if not self._apply_import_delta(delta):
            self.myint = delta

    def changed_from_default(self) -> bool:
        if self.do_import:
            return True
        return self._default != self.myint

    def get_type_str(self):
        return "Int"

    def update_xml(self):
        super().update_xml()
        if self.xml is not None:
            self.xml.text = str(self.myint)

    def __repr__(self):
        return repr(self.myint)


class WaNoItemBoolModel(AbstractWanoModel):
    def __init__(self, *args, **kwargs):
        super(WaNoItemBoolModel, self).__init__(*args, **kwargs)
        self.xml = None
        self.mybool = False
        self._default = False

    def parse_from_xml(self, xml):
        self.xml = xml
        bool_as_text = self.xml.text
        if bool_as_text.lower() == "true":
            self.mybool = True
        else:
            self.mybool = False
        self._default = self.mybool
        super().parse_from_xml(xml)

    def get_data(self):
        return self.mybool

    def set_data(self, data):
        self.mybool = data
        super(WaNoItemBoolModel, self).set_data(data)

    def get_type_str(self):
        return "Boolean"

    def __getitem__(self, item):
        return None

    def get_delta_to_default(self):
        return self.mybool

    def get_secure_schema(self) -> Optional[str]:
        schema = {self.name: {"type": "boolean"}}
        return schema

    def apply_delta(self, delta):
        self.mybool = delta

    def changed_from_default(self) -> bool:
        return self.mybool != self._default

    def update_xml(self):
        if self.mybool:
            self.xml.text = "True"
        else:
            self.xml.text = "False"


class WaNoItemFileModel(AbstractWanoModel):
    def __init__(self, *args, **kwargs):
        super(WaNoItemFileModel, self).__init__(*args, **kwargs)
        self.xml = None
        self.is_local_file = True
        self.mystring = "FileData"
        self._default = self.mystring
        self.logical_name = "FileDataLogical"
        self._local_file_default = True
        self._cached_logical_name = "unset"

    def parse_from_xml(self, xml):
        self.xml = xml
        self.is_local_file = True
        self.mystring = self.xml.text
        self.logical_name = self.xml.attrib["logical_filename"]
        if "local" in self.xml.attrib:
            if self.xml.attrib["local"].lower() == "true":
                self.is_local_file = True
            else:
                self.is_local_file = False
        else:
            self.xml.attrib["local"] = "True"
        self._local_file_default = self.is_local_file
        self._default = self.mystring
        super().parse_from_xml(xml)

    def get_data(self):
        return self.mystring

    def set_data(self, data):
        self.mystring = str(data)
        super(WaNoItemFileModel, self).set_data(data)

    def get_secure_schema(self) -> Optional[str]:
        raise SecurityError("WaNoFile not allowed in Secure Mode. Aborting.")
        schema = {self.name: {"type": "string"}}
        return schema

    def __getitem__(self, item):
        return None

    def _class_to_uri(self):
        if self.is_local_file:
            outstring = f"local://{self.mystring}"
        else:
            outstring = f"global://{self.mystring}"
        return outstring

    def _uri_to_class(self, uri):
        if uri.startswith("local://"):
            startat = 8
            self.is_local_file = True
        else:
            assert uri.startswith(
                "global://"
            ), "URI needs to either start with local or global"
            startat = 9
            self.is_local_file = False
            if self.view is not None:
                self.view.set_disable(True)
        self.mystring = uri[startat:]

    def set_local(self, is_local):
        self.is_local_file = is_local
        if self.is_local_file:
            self.xml.attrib["local"] = "True"
        else:
            self.xml.attrib["local"] = "False"

    def get_local(self):
        return self.is_local_file

    def get_type_str(self):
        if self.visible():
            return "File"
        else:
            return "FString"

    def update_xml(self):
        self.xml.text = self.mystring

    def __repr__(self):
        return repr(self.mystring)

    def get_rendered_wano_data(self):
        return self.logical_name

    def render(self, rendered_wano, path, submitdir):
        if self.view is not None:
            self.view.line_edited()
        rendered_logical_name = Template(
            self.logical_name, newline_sequence="\n"
        ).render(wano=rendered_wano, path=path)
        outfile = None
        if not self.visible():
            if sys.version_info >= (3, 0):
                outfile = rendered_logical_name
            else:
                outfile = rendered_logical_name.encode("utf-8")
        if outfile is not None:
            self._cached_logical_name = outfile
            return outfile
        # Upload and copy
        if submitdir is not None and self.is_local_file:
            destdir = os.path.join(submitdir, "inputs")
            mkdir_p(destdir)
            destfile = os.path.join(destdir, rendered_logical_name)
            # print("Copying",self._root.wano_dir_root,rendered_logical_name,destdir)
            try:
                shutil.copy(self.mystring, destfile)
            except IsADirectoryError as e:
                raise WorkflowSubmitError(
                    "%s points to a directory, but a filename was expected in %s"
                    % (e.filename, self.path)
                )
        if sys.version_info >= (3, 0):
            outfile = rendered_logical_name
        else:
            outfile = rendered_logical_name.encode("utf-8")
        self._cached_logical_name = outfile
        return outfile

    def cached_logical_name(self):
        return self._cached_logical_name

    def model_to_dict(self, outdict):
        outdict["logical_name"] = self._cached_logical_name
        super().model_to_dict(outdict)

    def get_delta_to_default(self):
        return self._class_to_uri()

    def apply_delta(self, delta):
        self._uri_to_class(delta)

    def changed_from_default(self) -> bool:
        return (
            self._local_file_default != self.is_local_file
            or self.mystring != self._default
        )


class WaNoItemScriptFileModel(WaNoItemFileModel):
    def __init__(self, *args, **kwargs):
        super(WaNoItemScriptFileModel, self).__init__(*args, **kwargs)
        self.xml = None
        self.mystring = ""
        self.logical_name = self.mystring

    def parse_from_xml(self, xml):
        self.xml = xml
        self.mystring = self.xml.text
        self.logical_name = self.mystring
        super().parse_from_xml(xml)

    def get_path(self):
        root_dir = os.path.join(self._root.get_dir_root(), "inputs")
        return os.path.join(root_dir, self.mystring)

    def save_text(self, text):
        root_dir = os.path.join(self._root.get_dir_root(), "inputs")
        mkdir_p(root_dir)
        with open(self.get_path(), "w", newline="\n") as outfile:
            outfile.write(text)

    def get_type_str(self):
        return "File"

    def get_as_text(self):
        fullpath = self.get_path()
        content = ""
        try:
            # print("Reading script from ",fullpath)
            with open(fullpath, "r", newline="\n") as infile:
                content = infile.read()
            # print("Contents were",content)
            return content
        except FileNotFoundError:
            return ""

    def render(self, rendered_wano, path, submitdir):
        rendered_logical_name = Template(
            self.logical_name, newline_sequence="\n"
        ).render(wano=rendered_wano, path=path)
        if submitdir is not None:
            destdir = os.path.join(submitdir, "inputs")
            mkdir_p(destdir)
            destfile = os.path.join(destdir, rendered_logical_name)
            with open(destfile, "wt", newline="\n") as out:
                out.write(self.get_as_text())
        self._cached_logical_name = rendered_logical_name
        return rendered_logical_name


class WaNoItemStringModel(AbstractWanoModel):
    def __init__(self, *args, **kwargs):
        super(WaNoItemStringModel, self).__init__(*args, **kwargs)
        self._output_filestring = ""
        self.xml = None
        self.mystring = "unset"
        self._default = self.mystring

    def parse_from_xml(self, xml):
        self.xml = xml
        self.mystring = self.xml.text
        self._default = self.mystring
        if "dynamic_output" in self.xml.attrib:
            self._output_filestring = self.xml.attrib["dynamic_output"]
            self._root.register_outputfile_callback(self.get_extra_output_files)
        super().parse_from_xml(xml)

    def get_extra_output_files(self):
        extra_output_files = []
        if self._output_filestring != "":
            extra_output_files.append(self._output_filestring % self.mystring)
        return extra_output_files

    def get_data(self):
        return self.mystring

    def set_data(self, data):
        self.mystring = str(data)
        super(WaNoItemStringModel, self).set_data(data)

    def __getitem__(self, item):
        return None

    def get_delta_to_default(self):
        import_delta = self._get_import_delta()
        if import_delta:
            return import_delta
        return self.mystring

    def apply_delta(self, delta):
        if not self._apply_import_delta(delta):
            self.mystring = delta

    def changed_from_default(self) -> bool:
        if self.do_import:
            return True
        return self.mystring != self._default

    def get_type_str(self):
        return "String"

    def update_xml(self):
        super().update_xml()
        self.xml.text = self.mystring

    def __repr__(self):
        return repr(self.mystring)

    def get_secure_schema(self) -> Optional[str]:
        schema = {self.name: {"type": "string"}}
        return schema


class WaNoThreeRandomLetters(WaNoItemStringModel):
    def __init__(self, *args, **kwargs):
        super(WaNoThreeRandomLetters, self).__init__(*args, **kwargs)
        self.xml = None
        self.mystring = None

        if self.mystring == "" or self.mystring is None:
            self.mystring = self._generate_default_string()
            self.set_data(self.mystring)

    def parse_from_xml(self, xml):
        self.xml = xml
        self.mystring = self.xml.text
        super().parse_from_xml(xml)

        if self.mystring == "" or self.mystring is None:
            self.mystring = self._generate_default_string()
            self.set_data(self.mystring)

    def _generate_default_string(self):
        from random import choice
        import string

        only_letters = string.ascii_uppercase
        letters_and_numbers = string.ascii_uppercase + string.digits
        return "".join(
            [
                choice(only_letters),
                choice(letters_and_numbers),
                choice(letters_and_numbers),
            ]
        )

    def set_data(self, data):
        self.mystring = str(data)
        if len(self.mystring) > 3:
            self.mystring = self.mystring[0:3]
            if self.view is not None:
                self.view.init_from_model()

        super(WaNoThreeRandomLetters, self).set_data(self.mystring)

    def __repr__(self):
        return repr(self.mystring)


_mapping_tag = yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG


def dict_representer(dumper, data):
    return dumper.represent_dict(data.items())


def dict_constructor(loader, node):
    return collections.OrderedDict(loader.construct_pairs(node))


yaml.add_representer(collections.OrderedDict, dict_representer)
yaml.add_constructor(_mapping_tag, dict_constructor)

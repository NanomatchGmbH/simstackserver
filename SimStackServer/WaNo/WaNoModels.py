#!/usr/bin/python
# -*- coding: utf-8 -*-

#from pyura.pyura.helpers import trace_to_logger
import logging
import re
from functools import partial
from os.path import join

from SimStackServer.Reporting.ReportRenderer import ReportRenderer
from SimStackServer.Util.XMLUtils import is_regular_element
from SimStackServer.WorkflowModel import WorkflowExecModule, StringList, WorkflowElementList

import collections

from TreeWalker.TreeWalker import TreeWalker
from SimStackServer.WaNo.AbstractWaNoModel import AbstractWanoModel, OrderedDictIterHelper
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


class FileNotFoundErrorSimStack(FileNotFoundError):
    pass

from SimStackServer.WaNo.WaNoTreeWalker import PathCollector, subdict_skiplevel, subdict_skiplevel_to_type, \
    subdict_skiplevel_to_aiida_type
from TreeWalker.flatten_dict import flatten_dict
from TreeWalker.tree_list_to_dict import tree_list_to_dict


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
            name = child.attrib['name']
            ModelClass = SimStackServer.WaNo.WaNoFactory.WaNoFactory.get_model_class(child.tag)
            ViewClass = SimStackServer.WaNo.WaNoFactory.WaNoFactory.get_qt_view_class(child.tag)
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

    def get_data(self):
        return self.wano_dict

    def set_data(self, wano_dict):
        self.wano_dict = wano_dict

    def wanos(self):
        return self.wano_dict.values()

    def get_type_str(self):
        return "Dict"

    #def __repr__(self):
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
        super(WaNoChoiceModel,self).__init__(*args,**kwargs)
        self.choices = []
        self.chosen=0


    def parse_from_xml(self, xml):
        super().parse_from_xml(xml)
        self.xml = xml
        for child in self.xml.iter("Entry"):
            if not is_regular_element(child):
                continue
            myid = int(child.attrib["id"])
            self.choices.append(child.text)
            assert(len(self.choices) == myid + 1)
            if "chosen" in child.attrib:
                if child.attrib["chosen"].lower() == "true":
                    self.chosen = myid

    def __getitem__(self, item):
        return None

    def get_type_str(self):
        return "String"

    def get_data(self):
        try:
            return self.choices[self.chosen]
        except IndexError as e:
            print("Invalid choice in %s. Returning choice 0"%self.name)
            return self.choices[0]

    def set_chosen(self,choice):
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

class WaNoDynamicChoiceModel(WaNoChoiceModel):
    def __init__(self, *args, **kwargs):
        super(WaNoDynamicChoiceModel,self).__init__(*args,**kwargs)
        self._collection_path = ""
        self._subpath = ""
        self.choices = ["uninitialized"]
        self.chosen = -1
        self._connected = True
        self._updating = False
        self._registered = False
        self._registered_paths = []

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
            root.register_callback(self._collection_path, self._update_choices)
            self._registered = True

    def _update_choices(self, changed_path):
        if not self._connected:
            return 
        if not changed_path.startswith(self._collection_path) and not changed_path == "force":
            return

        self._updating = True
        wano_listlike = self._root.get_value(self._collection_path)
        self.choices = []
        numchoices = len(wano_listlike)
        register_paths = []
        for myid in range(0,numchoices):
            query_string = "%s.%d.%s"% (self._collection_path,myid,self._subpath)
            register_paths.append(query_string)
            self.choices.append(self._root.get_value(query_string).get_data())

        delete_later = []
        for path in self._registered_paths:
            if path not in register_paths:
                self._root.unregister_callback(path, self._update_choices)
                delete_later.append(path)
        for path in delete_later:
            self._registered_paths.remove(path)

        for path in register_paths:
            if path in self._registered_paths:
                continue
            self._root.register_callback(path, self._update_choices)
            self._registered_paths.append(path)

        if len(self.choices) == 0:
            self.choices = ["uninitialized"]

        if len(self.choices) <= self.chosen:
            self.chosen = 0

        #Workaround because set_chosen kills chosen
        if not self.view is None:
            self.view.init_from_model()

        self._updating = False


    def set_chosen(self,choice):
        if not self._connected:
            return
        if self._updating:
            return
        self.chosen = int(choice)
        if len (self.choices) > self.chosen:
            self.set_data(self.choices[self.chosen])


    def update_xml(self):
        self.xml.attrib["chosen"] = str(self.chosen)

    def decommission(self):
        if self._registered:
            self.get_root().unregister_callback(self._collection_path, self._update_choices)
            self._registered = False
        for path in self._registered_paths:
            self._root.unregister_callback(path, self._update_choices)
        self._registered_paths.clear()

        super().decommission()



class WaNoMatrixModel(AbstractWanoModel):
    def __init__(self, *args, **kwargs):
        super(WaNoMatrixModel, self).__init__(*args, **kwargs)

        self.rows = 0
        self.cols = 0
        self.col_header = None
        self.row_header = None
        self.storage = None

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
        except ValueError as e:
            return f'"{value}"'

    def _cast_to_correct_type(self, value):
        try:
            a = float(value)
            return a
        except ValueError as e:
            return str(value)

    def set_data(self,i,j,data):
        self.storage[i][j] = self._cast_to_correct_type(data)

    def _fromstring(self,stri):
        list_of_lists = ast.literal_eval(stri)
        if not isinstance(list_of_lists,list):
            raise SyntaxError("Expected list of lists")
        for i in range(len(list_of_lists)):
            for j in range(len(list_of_lists[i])):
                list_of_lists[i][j] = self._cast_to_correct_type(list_of_lists[i][j])
        return list_of_lists

    def __getitem__(self,item):
        return self._tostring(self.storage)

    def get_type_str(self):
        return None

    def get_data(self):
        return self._tostring(self.storage)

    def update_xml(self):
        self.xml.text = self._tostring(self.storage)


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
            ModelClass = SimStackServer.WaNo.WaNoFactory.WaNoFactory.get_model_class(child.tag)
            ViewClass = SimStackServer.WaNo.WaNoFactory.WaNoFactory.get_qt_view_class(child.tag)
            model = ModelClass()
            model.set_view_class(ViewClass)
            model.parse_from_xml(child)
            start_path = [*self.path.split(".")] + [str(current_id)]
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

    def update_xml(self):
        for wano in self.wano_list:
            wano.update_xml()

    def decommission(self):
        for wano in self.wano_list:
            wano.decommission()
        super().decommission()

    #def disconnectSignals(self):
    #    super(WaNoModelListLike,self).disconnectSignals()
    #    for wano in self.wano_list:
    #        wano.disconnectSignals()

class WaNoNoneModel(AbstractWanoModel):
    def __init__(self, *args, **kwargs):
        super(WaNoNoneModel, self).__init__(*args, **kwargs)

    def parse_from_xml(self, xml):
        self.xml = xml

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

    def __repr__(self):
        return ""


class WaNoSwitchModel(WaNoModelListLike):
    def __init__(self, *args, **kwargs):
        super(WaNoSwitchModel, self).__init__(*args, **kwargs)
        self._switch_name_list = []
        self._names_list = []
        self._switch_path = None
        self._visible_thing = -1
        self._registered = False
        #self._name = "unset"

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

    #def __getitem__(self, item):
    #    return self.wano_list[self._visible_thing].__getitem__(item)

    def __iter__(self):
        return self.wano_list.__iter__()

    def items(self):
        return enumerate(self.wano_list)

    def __reversed__(self):
        return self.wano_list.__reversed__()

    def get_selected_id(self):
        if self._visible_thing >= 0:
            return self._visible_thing
        else:
            return 0

    def _evaluate_switch_condition(self,changed_path):
        if changed_path != self._switch_path and not changed_path == "force":
            return
        #print("Evaluating mypath %s for changed_path %s"%(self._switch_path, changed_path))
        visible_thing_string = self._root.get_value(self._switch_path).get_data()
        try:
            visible_thing = self._switch_name_list.index(visible_thing_string)
            self._visible_thing = visible_thing
            self._name = self._names_list[self._visible_thing]
            if self._view is not None:
                self._view.init_from_model()
        except (IndexError, KeyError) as e:
            print("This will throw!",e)
            pass

    def get_type_str(self):
        if self._visible_thing >= 0:
            #print(self._visible_thing, self.wano_list, self._name, self.path)
            return self.wano_list[self._visible_thing].get_type_str()
        return "unset"

    def get_data(self):
        if self._visible_thing >= 0:
            return self.wano_list[self._visible_thing].get_data()
        return "unset"

    def set_path(self, path):
        super().set_path(path)
        self._switch_path = Template(self._switch_path).render(path = self._path.split("."))
        if not self._registered:
            self._root.register_callback(self._switch_path, self._evaluate_switch_condition)
            self._registered = True

    def get_parent(self):
        return self._parent

    def set_parent(self, parent):
        super().set_parent(parent)

    def set_root(self, root):
        super().set_root(root)

    def _parse_switch_conditions(self, xml):
        self._switch_path  = xml.attrib["switch_path"]

    def decommission(self):
        self._root.unregister_callback(self._switch_path, self._evaluate_switch_condition)
        self._registered = False
        for wano in self.wano_list:
            wano.decommission()
        super().decommission()


class MultipleOfModel(AbstractWanoModel):
    def __init__(self, *args, **kwargs):
        super(MultipleOfModel, self).__init__(*args, **kwargs)

        self.first_xml_child = None
        self.list_of_dicts = []


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

    def number_of_multiples(self):
        return len(self.list_of_dicts)

    def last_item_check(self):
        return len(self.list_of_dicts) == 1

    def parse_one_child(self, child, build_view = False):
        #A bug still exists, which allows visibility conditions to be fired prior to the existence of the model
        #but this is transient.
        wano_temp_dict = OrderedDictIterHelper()
        current_id = len(self.list_of_dicts)
        #fp = "%s.%d"%(self.full_path,current_id)
        for cchild in child:
            ModelClass = SimStackServer.WaNo.WaNoFactory.WaNoFactory.get_model_class(cchild.tag)
            ViewClass = SimStackServer.WaNo.WaNoFactory.WaNoFactory.get_qt_view_class(cchild.tag)
            model = ModelClass()
            model.set_view_class(ViewClass)
            model.parse_from_xml(cchild)
            name = cchild.attrib['name']
            start_path = [*self.path.split(".")] + [str(current_id),model.name ]

            model.set_name(name)
            rootview = None
            if build_view:
                self.get_root()
                model.set_root(self.get_root())

                model, rootview = SimStackServer.WaNo.WaNoFactory.wano_constructor_helper(model, start_path = start_path, parent_view = self.view)
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

    def add_item(self):
        before = self._root.block_signals(True)
        my_xml = copy.copy(self.first_xml_child)
        my_xml.attrib["id"] = str(len(self.list_of_dicts))
        self.xml.append(my_xml)
        model_dict = self.parse_one_child(my_xml, build_view=True)
        self.list_of_dicts.append(model_dict)
        self._root.block_signals(before)
        self.get_root().datachanged_force()
        if self.view is not None:
            self.view.init_from_model()



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
    def _exists_read_load(self, object, filename):
        if os.path.exists(filename):
            object.load(filename)
        else:
            object.make_default_list()
            object.save(filename)

    def set_parent_wf(self, parent_wf):
        self._parent_wf = parent_wf

    def get_parent_wf(self):
        return self._parent_wf

    def __init__(self, *args, **kwargs):
        super(WaNoModelRoot, self).__init__(*args, **kwargs)
        self._logger = logging.getLogger("WaNoModelRoot")
        self._datachanged_callbacks = {}
        self._outputfile_callbacks = []
        self._notifying = False
        self._unregister_list = []
        self._register_list = []
        self._wano_dir_root = kwargs["wano_dir_root"]
        self._my_export_paths = []
        self._block_signals = False

        if "model_only" in kwargs and kwargs["model_only"] is True:
            pass
        else:
            # We want to allow construction without QT view imports, which are happening here
            from WaNo.view.PropertyListView import ResourceTableModel, ImportTableModel, ExportTableModel
            self.resources = ResourceTableModel(parent=None,wano_parent=self)

            self.import_model = ImportTableModel(parent=None,wano_parent=self)
            self.import_model.make_default_list()

            self.export_model = ExportTableModel(parent=None,wano_parent=self)
            self.export_model.make_default_list()

            imports_fn = os.path.join(self._wano_dir_root, "imports.yml")
            self._exists_read_load(self.import_model, imports_fn)

            exports_fn = os.path.join(self._wano_dir_root, "exports.yml")
            self._exists_read_load(self.export_model, exports_fn)

            resources_fn = os.path.join(self._wano_dir_root, "resources.yml")
            self._exists_read_load(self.resources, resources_fn)
        self._root = self

        self.rendered_exec_command = ""

        self.input_files = []
        self.output_files = []

        self.metas = OrderedDictIterHelper()

    def block_signals(self,true_or_false):
        before = self._block_signals
        self._block_signals = true_or_false
        return before

    def parse_from_xml(self, xml):
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
            self.input_files.append((child.attrib["logical_filename"],child.text))

        el = self.full_xml.find("./WaNoMeta")
        if not el is None:
            self.metas = xmltodict.parse(etree.tostring(el))

        self.exec_command = self.full_xml.find("WaNoExecCommand").text
        for child in self.full_xml.find("WaNoExecCommand"):
            raise WaNoParseError("Another XML element was found in WaNoExecCommand. (This can be comments or open and close tags). This is not supported. Aborting Parse.")
        #print("My Exec Command is: %s"%self.exec_command)

        super().parse_from_xml(xml=subxml)

    def _tidy_lists(self):
        while len(self._unregister_list) > 0:
            key,func = self._unregister_list.pop()
            self.unregister_callback(key,func)

        while len(self._register_list) > 0:
            key,func = self._register_list.pop()
            self.register_callback(key,func)


    def notify_datachanged(self, path):
        if self._block_signals:
            return
        if self._notifying:
            return

        self._tidy_lists()

        #print("Checking changed path %s"%path)
        if "unset" in path:
            print("Found unset in path %s"%path)
        self._notifying = True
        if path == "force":
            for callbacks in self._datachanged_callbacks.values():
                for callback in callbacks:
                    callback(path)

        if path in self._datachanged_callbacks:
            for callback in self._datachanged_callbacks[path]:
                callback(path)
        self._notifying = False

        self._tidy_lists()

    def register_callback(self, path, callback_function):
        if self._notifying:
            toregister = (path, callback_function)
            if not toregister in self._register_list:
                self._register_list.append(toregister)
        else:
            if path not in self._datachanged_callbacks:
                self._datachanged_callbacks[path] = []

            if callback_function not in self._datachanged_callbacks[path]:
                self._datachanged_callbacks[path].append(callback_function)

    def unregister_callback(self, path, callback_function):
        assert path in self._datachanged_callbacks, "When unregistering a function, it has to exist in datachanged_callbacks."
        assert callback_function in self._datachanged_callbacks[path], "Function not found in callbacks. Has to exist."
        #print("Removing %s for %s"%(path, callback_function))
        if self._notifying:
            self._unregister_list.append((path, callback_function))
        else:
            self._datachanged_callbacks[path].remove(callback_function)

    def get_type_str(self):
        return "WaNoRoot"

    def get_resource_model(self):
        return self.resources

    def get_import_model(self):
        return self.import_model

    def get_export_model(self):
        return self.export_model

    def register_outputfile_callback(self,function):
        self._outputfile_callbacks.append(function)

    def get_output_files(self, only_static = False):
        return_files = []

        rendered_wano = None
        for outputfile in self.output_files:
            if "{{" in outputfile and "}}" in outputfile:
                if rendered_wano is None:
                    rendered_wano = self.wano_walker()
                outfile = Template(outputfile,newline_sequence='\n').render(wano = rendered_wano)
                return_files.append(outfile)
            else:
                return_files.append(outputfile)

        if only_static:
            return return_files

        return_files = return_files + [ a[0] for a in self.export_model.get_contents() ]
        for callback in self._outputfile_callbacks:
            return_files += callback()
        return return_files

    def datachanged_force(self):
        self.notify_datachanged("force")

    def save_xml(self,filename):
        print("Writing to ",filename)
        self.wano_dir_root = os.path.dirname(filename)
        success = False
        try:
            with open(filename,'w',newline='\n') as outfile:
                outfile.write(etree.tostring(self.full_xml,pretty_print=True).decode("utf-8"))
            success = True
            resources_fn = os.path.join(self.wano_dir_root, "resources.yml")
            self.resources.save(resources_fn)

            imports_fn = os.path.join(self.wano_dir_root, "imports.yml")
            self.import_model.save(imports_fn)

            exports_fn = os.path.join(self.wano_dir_root, "exports.yml")
            self.export_model.save(exports_fn)

        except Exception as e:
            print(e)
        return success

    def wano_walker_paths(self,parent = None, path = "" , output = []):
        if (parent == None):
            parent = self

        if isinstance(parent, WaNoSwitchModel):
            parent = parent[parent.get_selected_id()]

        listlike, dictlike = self._listlike_dictlike(parent)
        if listlike:
            my_list = []
            for key, wano in parent.items():
                mypath = copy.copy(path)
                if mypath == "":
                    mypath = "%s" % (key)
                else:
                    mypath = "%s.%s" % (mypath, key)
                self.wano_walker_paths(parent=wano, path=mypath,output=output)

        elif dictlike:
            for key,wano in parent.items():
                mypath = copy.copy(path)
                if hasattr(wano,"name"):
                    #Actual dict
                    key = wano.name
                #else list
                if mypath == "":
                    mypath="%s" %(key)
                else:
                    mypath = "%s.%s" % (mypath, key)
                self.wano_walker_paths(parent=wano,path=mypath,output=output)
        else:
            output.append((path,parent.get_type_str()))
        return output

    def wano_walker(self, parent = None, path = ""):
        if (parent == None):
            parent = self

        if isinstance(parent, WaNoSwitchModel):
            parent = parent[parent.get_selected_id()]
        #print(type(parent))
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
            for key,wano in parent.items():
                mypath = copy.copy(path)
                if hasattr(wano,"name"):
                    #Actual dict
                    key = wano.name
                #else list
                if mypath == "":
                    mypath="%s" %(key)
                else:
                    mypath = "%s.%s" % (mypath, key)
                my_dict[key] = self.wano_walker(parent=wano,path=mypath)
            return my_dict
        else:
            #print("%s %s" % (path, parent.get_data()))
            return parent.get_rendered_wano_data()

    def _listlike_dictlike(self,myobject):
        listlike = False
        dictlike = False
        if isinstance(myobject,collections.OrderedDict) or isinstance(myobject,dict):
            listlike = False
            dictlike = True
        elif isinstance(myobject,list):
            listlike = True
            dictlike = False

        if hasattr(myobject,"listlike"):
            listlike = myobject.listlike
        if hasattr(myobject, "dictlike"):
            dictlike = myobject.dictlike

        return listlike, dictlike

    @classmethod
    def _filename_is_global_var(cls, filename):
        if not re.match(r"^\$\{.*\}$",filename) is None:
            return True
        return False

    def wano_walker_render_pass(self, rendered_wano, parent = None, path = "",submitdir="",
                                flat_variable_list = None,
                                input_var_db = None,
                                output_var_db = None,
                                runtime_variables = None):
        if (parent == None):
            parent = self

        if isinstance(parent, WaNoSwitchModel):
            parent = parent[parent.get_selected_id()]
        #print(type(parent))
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

        listlike,dictlike = self._listlike_dictlike(parent)
        if listlike:
            my_list = []
            for key, wano in parent.items():
                mypath = copy.copy(path)
                if mypath == "":
                    mypath = "%s" % (key)
                else:
                    mypath = "%s.%s" % (mypath, key)
                my_list.append(self.wano_walker_render_pass(rendered_wano,parent=wano, path=mypath,submitdir=submitdir,flat_variable_list=flat_variable_list, input_var_db = input_var_db, output_var_db = output_var_db, runtime_variables = runtime_variables))
            return my_list
        elif dictlike:
            my_dict = {}
            for key,wano in parent.items():
                mypath = copy.copy(path)
                if hasattr(wano,"name"):
                    #Actual dict
                    key = wano.name
                #else list
                if mypath == "":
                    mypath="%s" %(key)
                else:
                    mypath = "%s.%s" % (mypath, key)
                my_dict[key] = self.wano_walker_render_pass(rendered_wano,parent=wano, path=mypath, submitdir=submitdir, flat_variable_list=flat_variable_list, input_var_db = input_var_db, output_var_db = output_var_db, runtime_variables = runtime_variables)
            return my_dict
        else:
            # We should avoid merging and splitting. It's useless, we only need splitpath anyways
            splitpath = path.split(".")
            #path is complete here, return path
            rendered_parent =  parent.render(rendered_wano,splitpath, submitdir=submitdir)
            if isinstance(rendered_parent,str) and input_var_db is not None and output_var_db is not None:
                if rendered_parent.startswith("${") and rendered_parent.endswith("}"):
                    varname = rendered_parent[2:-1]

                    if runtime_variables is not None:
                        for runtime_varname, runtime_varvalue in runtime_variables.items():
                            varname = varname.replace(runtime_varname,runtime_varvalue)
                            rendered_parent = varname

                    if varname in input_var_db:
                        rendered_parent = input_var_db[varname]
                    if varname in output_var_db:
                        rendered_parent = output_var_db[varname]

            if flat_variable_list is not None:
                rendered_parent_jsdl = rendered_parent
                if parent.get_type_str() == "File":
                    filename = parent.get_data()
                    if parent.get_local():
                        pass
                        #to_upload = os.path.join(submitdir, "workflow_data")
                        #cp = os.path.commonprefix([to_upload, filename])
                        #relpath = os.path.relpath(filename, cp)
                        #print("relpath was: %s"%relpath)
                        #filename= "c9m:${WORKFLOW_ID}/%s" % relpath
                        #filename = "BFT:${STORAGE_ID}/%s" % relpath
                        #filename = os.path.join("inputs",relpath)
                        #Absolute filenames will be replace with BFT:STORAGEID etc. below.
                    elif not self._filename_is_global_var(filename):
                        if "outputs/" in filename:
                            # Newer handling, not rewriting filename, because it's already taken care of
                            filename = "c9m:${STORAGE}/workflow_data/%s" % (filename)
                        else:
                            last_slash = filename.rfind("/")
                            first_part = filename[0:last_slash]
                            second_part = filename[last_slash+1:]
                            # We cut this here to add the outputs folder. This is a bit hacky - we should differentiate between display name and
                            # name on cluster
                            filename = "c9m:${STORAGE}/workflow_data/%s/outputs/%s"%(first_part,second_part)

                    rendered_parent_jsdl = (rendered_parent,filename)

                flat_variable_list.append((path,parent.get_type_str(),rendered_parent_jsdl))
            return rendered_parent


    def prepare_files_submission(self,rendered_wano, basefolder):
        basefolder = os.path.join(basefolder,"inputs")
        mkdir_p(basefolder)
        raw_xml = os.path.join(basefolder, self._name + ".xml")
        with open(raw_xml, 'wt') as outfile:
            outfile.write(etree.tounicode(self.full_xml, pretty_print=True))

        for remote_file,local_file in self.input_files:
            comp_filename = os.path.join(self.wano_dir_root,local_file)
            comp_filename = os.path.abspath(comp_filename)
            comp_dir = os.path.dirname(comp_filename)
            comp_basename = os.path.basename(comp_filename)

            joined_filename = os.path.join(comp_dir,comp_basename)

            if not os.path.exists(os.path.join(joined_filename)):
                print("File <%s> not found on disk, please check for spaces before or after the filename."%comp_filename)
                raise FileNotFoundErrorSimStack("File <%s> not found on disk, please check for spaces before or after the filename."%comp_filename)

            outfile = os.path.join(basefolder,remote_file)
            dirn=os.path.dirname(outfile)
            mkdir_p(dirn)
            print("Copying from %s to %s"%(comp_filename, dirn))
            shutil.copy(comp_filename, dirn)

    def flat_variable_list_to_jsdl(self,fvl,basedir,stageout_basedir):
        files = []

        local_stagein_files = []
        runtime_stagein_files = []
        runtime_stageout_files = []


        for myid,(logical_filename, source) in enumerate(self.input_files):
            fvl.append(("IFILE%d"%(myid),"File",(logical_filename,source)))
            #local_stagein_files.append([logical_filename,source])

        for (varname,type,var) in fvl:
            if type == "File":
                log_path_on_cluster = var[1].replace('\\','/')
                if var[1].startswith("c9m:"):
                    runtime_stagein_files.append([var[0],log_path_on_cluster])
                elif self._filename_is_global_var(var[1]):

                    runtime_stagein_files.append([var[0], log_path_on_cluster])
                else:
                    if var[1].startswith("/"):
                        #In this case this will be a local import.
                        runtime_stagein_files.append(
                            [var[0], "${STORAGE}/workflow_data/%s/inputs/%s" % (stageout_basedir, var[0])])
                    else:
                        runtime_stagein_files.append([var[0], "${STORAGE}/workflow_data/%s/inputs/%s"% (stageout_basedir, var[1])])
                    #print(runtime_stagein_files,var)
            else:
                #These should be NON posix arguments in the end
                varname.replace(".","_")
        #xmlfile = self._name + ".xml"
        #runtime_stagein_files.append([self._name + ".xml","${STORAGE}/workflow_data/%s/inputs/%s" % (stageout_basedir, "rendered_wano.yml)])

        for otherfiles in self.get_import_model().get_contents():
            name,importloc,tostage = otherfiles[0],otherfiles[1],otherfiles[2]
            if self._filename_is_global_var(importloc):
                runtime_stagein_files.append([name,importloc])
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
                    second_part = importloc[last_slash + 1:]
                    filename = "${STORAGE}/workflow_data/%s/outputs/%s" % (first_part, second_part)

                #print("In runtime stagein %s"%filename)
                runtime_stagein_files.append([tostage, filename])


        #for filename in self.output_files + [ a[0] for a in self.export_model.get_contents() ]:
        for filename in self.get_output_files(only_static=False):
            #runtime_stageout_files.append([filename,"${STORAGE}/workflow_data/%s/outputs/%s"%(stageout_basedir,filename)])
            runtime_stageout_files.append([filename, filename])

        _runtime_stagein_files = []
        for ft in runtime_stagein_files:
            _runtime_stagein_files.append(["StringList",StringList(ft)])
        runtime_stagein_files = _runtime_stagein_files

        _runtime_stageout_files = []
        for ft in runtime_stageout_files:
            _runtime_stageout_files.append(["StringList",StringList(ft)])
        runtime_stageout_files = _runtime_stageout_files

        """
        _local_stagein_files = []
        for ft in local_stagein_files:
            _local_stagein_files.append(["StringList",StringList(ft)])
        local_stagein_files = _local_stagein_files
        """

        
        wem = WorkflowExecModule(given_name = self.name, resources = self.resources.render_to_simstack_server_model(),
                           inputs = WorkflowElementList(runtime_stagein_files),# + local_stagein_files),
                           outputs = WorkflowElementList(runtime_stageout_files),
                           exec_command = self.rendered_exec_command
                           )

        return None , wem, local_stagein_files
        #print(etree.tostring(job_desc, pretty_print=True).decode("utf-8"))

    def render_wano(self,submitdir,stageout_basedir=""):
        #We do two render passes in case values depend on each other
        rendered_wano = self.wano_walker()
        # We do two render passes, in case the rendering reset some values:
        fvl = []
        rendered_wano = self.wano_walker_render_pass(rendered_wano,submitdir=submitdir,flat_variable_list=fvl)
        #self.rendered_exec_command = Template(self.exec_command,newline_sequence='\n').render(wano = rendered_wano)
        #self.rendered_exec_command = self.rendered_exec_command.strip(' \t\n\r')
        self.rendered_exec_command = self.exec_command
        jsdl, wem, local_stagein_files = self.flat_variable_list_to_jsdl(fvl, submitdir,stageout_basedir)
        return rendered_wano,jsdl, wem, local_stagein_files
    
    def render_exec_command(self, rendered_wano):
        rendered_exec_command = Template(self.exec_command,newline_sequence='\n').render(wano = rendered_wano)
        rendered_exec_command = rendered_exec_command.strip(' \t\n\r')
        return rendered_exec_command + '\n'

    #@trace_to_logger
    def render_and_write_input_files(self,basefolder,stageout_basedir = ""):
        rendered_wano,jsdl, wem = self.render_wano(basefolder,stageout_basedir)
        self.prepare_files_submission(rendered_wano, basefolder)
        return jsdl

    def render_and_write_input_files_newmodel(self,basefolder,stageout_basedir = ""):
        rendered_wano, jsdl, wem, local_stagein_files = self.render_wano(basefolder, stageout_basedir)
        #pprint(local_stagein_files)
        self.prepare_files_submission(rendered_wano, basefolder)
        return jsdl, wem

    def get_value(self,uri):
        split_uri = uri.split(".")
        current = self.__getitem__(split_uri[0])
        for item in split_uri[1:]:
            current = current[item]
        return current

    def get_all_variable_paths(self, export = True):
        outdict = {}
        self.model_to_dict(outdict)
        tw = TreeWalker(outdict)
        skipdict = tw.walker(capture=True, path_visitor_function=None, subdict_visitor_function=subdict_skiplevel,
                             data_visitor_function=None)
        tw = TreeWalker(skipdict)
        pc = PathCollector()
        tw.walker(capture=False, path_visitor_function=pc.assemble_paths,
                  subdict_visitor_function=None,
                  data_visitor_function=None)

        if export:
            return pc.paths + self._my_export_paths
        else:
            return pc.paths

    def _get_paths_and_something_helper(self, subdict_visitor, deref_functor_path_collector):
        outdict = {}
        self.model_to_dict(outdict)
        tw = TreeWalker(outdict)
        skipdict = tw.walker(capture=True, path_visitor_function=None, subdict_visitor_function=subdict_visitor,
                             data_visitor_function=None)
        tw = TreeWalker(skipdict)
        pc = PathCollector()
        tw.walker(capture=False, path_visitor_function=None,
                  subdict_visitor_function=subdict_visitor,
                  data_visitor_function=deref_functor_path_collector(pc)
        )
        return pc.path_to_value

    def get_paths_and_data_dict(self):
        return self._get_paths_and_something_helper(subdict_skiplevel, lambda x : x.assemble_paths_and_values)

    def get_extra_inputs_aiida(self):
        outfiles = [ ftuple[0] for ftuple in self.input_files ]
        return outfiles

    def get_paths_and_type_dict_aiida(self):
        outdict = {}
        self.model_to_dict(outdict)
        outdict = tree_list_to_dict(outdict)
        tw = TreeWalker(outdict)
        skipdict = tw.walker(capture=True, path_visitor_function=None, subdict_visitor_function=subdict_skiplevel_to_type,
                             data_visitor_function=None)
        tw = TreeWalker(skipdict)
        pc = PathCollector()
        tw.walker(capture=False, path_visitor_function=None,
                  subdict_visitor_function=subdict_skiplevel_to_type,
                  data_visitor_function= pc.assemble_paths_and_values
                  )
        return pc.path_to_value

    def get_valuedict_with_aiida_types(self, aiida_files_by_relpath = None):
        if aiida_files_by_relpath is None:
            aiida_files_by_relpath = {}
        outdict = {}
        self.model_to_dict(outdict)
        outdict = tree_list_to_dict(outdict)
        tw = TreeWalker(outdict)
        svf = partial(subdict_skiplevel_to_aiida_type, aiida_files_by_relpath = aiida_files_by_relpath)
        skipdict = tw.walker(capture=True, path_visitor_function=None, subdict_visitor_function=svf,
                             data_visitor_function=None)
        return skipdict

    """
    def get_paths_and_type_dict_aiida(self):
        outdict = {}
        self.model_to_dict(outdict)
        outdict = tree_list_to_dict(outdict)
        tw = TreeWalker(outdict)
        skipdict = tw.walker(capture=True, path_visitor_function=None,
                             subdict_visitor_function=subdict_skiplevel_to_type,
                             data_visitor_function=None)
        tw = TreeWalker(skipdict)
        pc = PathCollector()
        tw.walker(capture=False, path_visitor_function=None,
                  subdict_visitor_function=subdict_skiplevel_to_type,
                  data_visitor_function=pc.assemble_paths_and_values
                  )
        return pc.path_to_value
        """

    def get_dir_root(self):
        return self._wano_dir_root

class WaNoVectorModel(AbstractWanoModel):
    def __init__(self, *args, **kwargs):
        super(WaNoVectorModel, self).__init__(*args, **kwargs)
        self.myvalues = float(kwargs['xml'].text)
        for child in self.xml:
            if not is_regular_element(child):
                continue
            my_id = int(child.attrib["id"])
            value = float(child.text)
            while (len(self.myvalues) <= my_id):
                self.myvalues.append(0.0)
            self.myvalues[my_id] = value


class WaNoItemFloatModel(AbstractWanoModel):
    def __init__(self, *args, **kwargs):
        super(WaNoItemFloatModel, self).__init__(*args, **kwargs)
        self.myfloat = -100.0
        self.xml = None

    def parse_from_xml(self, xml):
        self.myfloat = float(xml.text)
        self.xml = xml
        super().parse_from_xml(xml)

    def get_data(self):
        return self.myfloat

    def set_data(self, data):
        self.myfloat = float(data)
        super(WaNoItemFloatModel, self).set_data(data)

    def __getitem__(self, item):
        return None

    def get_type_str(self):
        return "Float"

    def update_xml(self):
        super().update_xml()
        if self.xml is not None:
            self.xml.text = str(self.myfloat)

    def model_to_dict(self, outdict):
        outdict["data"] = str(self.myfloat)
        super().model_to_dict(outdict)

    def __repr__(self):
        return repr(self.myfloat)


class WaNoItemIntModel(AbstractWanoModel):
    def __init__(self, *args, **kwargs):
        super(WaNoItemIntModel, self).__init__(*args, **kwargs)
        self.myint = -10000000
        self.xml = None

    def parse_from_xml(self, xml):
        self.myint = float(xml.text)
        self.xml = xml
        super().parse_from_xml(xml)

    def get_data(self):
        return int(self.myint)

    def set_data(self, data):
        self.myint = int(data)
        super(WaNoItemIntModel,self).set_data(data)

    def __getitem__(self, item):
        return None

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

    def parse_from_xml(self, xml):
        self.xml = xml
        bool_as_text = self.xml.text
        if bool_as_text.lower() == "true":
            self.mybool = True
        else:
            self.mybool = False
        super().parse_from_xml(xml)

    def get_data(self):
        return self.mybool

    def set_data(self, data):
        self.mybool = data
        super(WaNoItemBoolModel,self).set_data(data)

    def get_type_str(self):
        return "Boolean"

    def __getitem__(self, item):
        return None

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
        self.logical_name = "FileDataLogical"
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
        super().parse_from_xml(xml)

    def get_data(self):
        return self.mystring

    def set_data(self, data):
        self.mystring = str(data)
        super(WaNoItemFileModel,self).set_data(data)

    def __getitem__(self, item):
        return None

    def set_local(self,is_local):
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
            return "String"

    def update_xml(self):
        self.xml.text = self.mystring

    def __repr__(self):
        return repr(self.mystring)

    def get_rendered_wano_data(self):
        return self.logical_name

    def render(self, rendered_wano, path, submitdir):
        if self.view is not None:
            self.view.line_edited()
        rendered_logical_name = Template(self.logical_name,newline_sequence='\n').render(wano=rendered_wano, path=path)
        outfile = None
        if not self.visible():
            if sys.version_info >= (3, 0):
                outfile = rendered_logical_name
            else:
                outfile = rendered_logical_name.encode("utf-8")
        if outfile is not None:
            self._cached_logical_name = outfile
            return outfile
        #Upload and copy
        #print(submitdir)
        if submitdir is not None and self.is_local_file:
            destdir = os.path.join(submitdir,"inputs")
            mkdir_p(destdir)
            destfile = os.path.join(destdir, rendered_logical_name)
            #print("Copying",self._root.wano_dir_root,rendered_logical_name,destdir)
            try:
                shutil.copy(self.mystring,destfile)
            except IsADirectoryError as e:
                raise WorkflowSubmitError("%s points to a directory, but a filename was expected in %s"%(e.filename,self.path))
        if sys.version_info >= (3,0):
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



class WaNoItemScriptFileModel(WaNoItemFileModel):
    def __init__(self,*args,**kwargs):
        super(WaNoItemScriptFileModel,self).__init__(*args,**kwargs)
        self.xml = None
        self.mystring = ""
        self.logical_name = self.mystring


    def parse_from_xml(self, xml):
        self.xml = xml
        self.mystring = self.xml.text
        self.logical_name = self.mystring
        super().parse_from_xml(xml)

    def get_path(self):
        root_dir = os.path.join(self._root.get_dir_root(),"inputs")
        return os.path.join(root_dir, self.mystring)

    def save_text(self,text):
        root_dir = os.path.join(self._root.get_dir_root(), "inputs")
        mkdir_p(root_dir)
        with open(self.get_path(),'w',newline='\n') as outfile:
            outfile.write(text)

    def get_type_str(self):
        return "File"

    def get_as_text(self):
        fullpath = self.get_path()
        content = ""
        try:
            #print("Reading script from ",fullpath)
            with open(fullpath,'r',newline='\n') as infile:
                content = infile.read()
            #print("Contents were",content)
            return content
        except FileNotFoundError:
            return ""

    def render(self, rendered_wano, path, submitdir):
        rendered_logical_name = Template(self.logical_name,newline_sequence='\n').render(wano=rendered_wano, path=path)
        if submitdir is not None:
            destdir = os.path.join(submitdir, "inputs")
            mkdir_p(destdir)
            destfile = os.path.join(destdir, rendered_logical_name)
            with open(destfile,'wt',newline='\n') as out:
                out.write(self.get_as_text())
        self._cached_logical_name = rendered_logical_name
        return rendered_logical_name


class WaNoItemStringModel(AbstractWanoModel):
    def __init__(self, *args, **kwargs):
        super(WaNoItemStringModel, self).__init__(*args, **kwargs)
        self._output_filestring = ""
        self.xml = None
        self.mystring = "unset"

    def parse_from_xml(self, xml):
        self.xml = xml
        self.mystring = self.xml.text
        if 'dynamic_output' in self.xml.attrib:
            self._output_filestring = self.xml.attrib["dynamic_output"]
            self._root.register_outputfile_callback(self.get_extra_output_files)
        super().parse_from_xml(xml)

    def get_extra_output_files(self):
        extra_output_files = []
        if self._output_filestring != "":
            extra_output_files.append(self._output_filestring%self.mystring)
        return extra_output_files

    def get_data(self):
        return self.mystring

    def set_data(self, data):
        self.mystring = str(data)
        super(WaNoItemStringModel,self).set_data(data)

    def __getitem__(self, item):
        return None

    def get_type_str(self):
        return "String"

    def update_xml(self):
        super().update_xml()
        self.xml.text = self.mystring

    def __repr__(self):
        return repr(self.mystring)

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
        return "".join([choice(only_letters),choice(letters_and_numbers),choice(letters_and_numbers)])

    def set_data(self, data):
        self.mystring = str(data)
        if len(self.mystring) > 3:
            self.mystring = self.mystring[0:3]
            if self.view != None:
                self.view.init_from_model()

        super(WaNoThreeRandomLetters,self).set_data(self.mystring)

    def __repr__(self):
        return repr(self.mystring)


_mapping_tag = yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG

def dict_representer(dumper, data):
    return dumper.represent_dict(data.items())

def dict_constructor(loader, node):
    return collections.OrderedDict(loader.construct_pairs(node))

yaml.add_representer(collections.OrderedDict, dict_representer)
yaml.add_constructor(_mapping_tag, dict_constructor)

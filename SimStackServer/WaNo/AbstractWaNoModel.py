#!/usr/bin/python
# -*- coding: utf-8 -*-
from collections import OrderedDict

from jinja2 import Template

from boolexp import Expression
import abc

class WaNoNotImplementedError(Exception):
    pass

class OrderedDictIterHelper(OrderedDict):
    def model_to_dict(self, outdict):
        for name, other_wano_model in self.items():
            suboutdict = {}
            other_wano_model.model_to_dict(suboutdict)
            outdict[name] = suboutdict



class AbstractWanoModel:
    def __init__(self, *args, **kwargs):

        self._parent_set = False
        self._path = ""

        self._view = None
        self._root = None
        self._is_wano = True
        self._name = "unset"

        self._visibility_condition = None
        self._visibility_var_path = None
        self._isvisible = True
        self._vc = None
        super(AbstractWanoModel, self).__init__()

    @property
    def name(self):
        return self._name

    @property
    def is_wano(self):
        return self._is_wano

    def set_view_class(self, ViewClass):
        self._vc = ViewClass

    def get_view_class(self):
        return self._vc

    @property
    def path(self):
        return self._path

    def set_path(self, path):
        self._path = path
        if self._visibility_condition is not None:
            self._visibility_var_path = Template(self._visibility_var_path).render(path = self._path.split("."))
            self._root.register_callback(self._visibility_var_path, self.evaluate_visibility_condition)

    def parse_from_xml(self, xml):
        self._name = xml.attrib["name"]
        if "visibility_condition" in xml.attrib:
            self._visibility_condition = xml.attrib["visibility_condition"]
            self._visibility_var_path  = xml.attrib["visibility_var_path"]

    def set_parent(self, parent):
        self._parent = parent
        self._parent_set = True

    def get_root(self):
        if self._root is None:
            raise ValueError("Requested root, which was None.")
        return self._root

    def set_root(self, root):
        self._root = root


    def visible(self):
        return self._isvisible

    def set_name(self, new_name):
        self._name = new_name

    def evaluate_visibility_condition(self,changed_path):
        if changed_path != self._visibility_var_path:
            if changed_path != "force":
                return

        value = self._root.get_value(self._visibility_var_path).get_data()
        truefalse = Expression(self._visibility_condition%value).evaluate()
        self._view.set_visible(truefalse)
        self._isvisible = truefalse

    def get_name(self):
        return self._name

    def get_parent(self):
        return self._parent

    def model_to_dict(self, outdict):
        outdict["Type"] = self.get_type_str()
        outdict["name"] = self._name
        if self.listlike:
            outdict["content"] = []
            for other_wano_model in self:
                suboutdict = {}
                other_wano_model.model_to_dict(suboutdict)
                outdict["content"].append(suboutdict)
        elif self.dictlike:
            outdict["content"] = {}
            for name, other_wano_model in self.items():
                suboutdict = {}
                other_wano_model.model_to_dict(suboutdict)
                outdict["content"][name] = suboutdict
        else:
            outdict["content"] = str(self.get_data())

    def dict_to_model(self):
        pass

    def get_dictlike(self):
        return {}

    def get_listlike(self):
        return []

    @property
    def listlike(self):
        return False

    @property
    def dictlike(self):
        return False

    # To access Wanomodels belonging to this one:
    # <Box>
    #   <Float name="me" />
    # <Box>
    # Box["me"] == Float Wano
    # Few remarks:
    # If There is a for loop, multiple of, etc., we require a specific syntax
    # multipleof should implement a list abc[0],abc[1]... etc.
    # everything else should be dict-like.
    # For trivial wanos without children this will return None
    @abc.abstractmethod
    def __getitem__(self, key):
        pass

    # Upon rendering the model might provide data different in comparison to the displayed one
    # (For example: the rendered wano only contains the logical filename and not local PC filename
    # By default however get_rendered_wano_data == get_data
    def get_rendered_wano_data(self):
        return self.get_data()

    def set_view(self, view):
        self._view = view

    @property
    def view(self):
        return self._view

    @abc.abstractmethod
    def get_data(self):
        pass

    @abc.abstractmethod
    def set_data(self,data):
        if self._root is not None:
            self._root.notify_datachanged(self._path)

    @abc.abstractmethod
    def get_type_str(self):
        raise NotImplementedError("get_type_str has to be implemented in childclass.")

    def render(self, rendered_wano, path, submitdir):
        return self.get_rendered_wano_data()

    @abc.abstractmethod
    def update_xml(self):
        pass

    def decommission(self):
        if self._view != None:
            self._view.decommission()

        if self._root is not None:
            if self._visibility_condition is not None:
                #print("unregistering")
                self._root.unregister_callback(self._visibility_var_path, self.evaluate_visibility_condition)

    def construct_children(self):
        pass

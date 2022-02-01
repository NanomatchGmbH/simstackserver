#!/usr/bin/python
# -*- coding: utf-8 -*-

import os
from lxml import etree

from SimStackServer.WaNo.WaNoTreeWalker import ViewCollector, WaNoTreeWalker
from SimStackServer.WaNo.MiscWaNoTypes import WaNoListEntry, get_wano_xml_path



def wano_without_view_constructor_helper(wmr, start_path = None):
    if start_path is None:
        start_path = []

    vc = ViewCollector()
    vc.set_start_path(start_path)
    newtw = WaNoTreeWalker(wmr)

    # Stage 3.5: Set Root Model
    vc.set_wano_model_root(wmr.get_root())
    newtw.walker(capture=False, path_visitor_function=None, subdict_visitor_function=vc.root_setter_subdict,
                 data_visitor_function=vc.root_setter_data)

    # Stage 2: Set all model paths
    newtw.walker(capture=False, path_visitor_function=None, subdict_visitor_function=vc.path_setter_subdict,
                 data_visitor_function=vc.path_setter_data)



    # Stage 2: Parent all models
    newtw.walker(capture=False, path_visitor_function=None, subdict_visitor_function=vc.assemble_model_parenter,
                 data_visitor_function=vc.data_visitor_model_parenter)

    return wmr

def wano_constructor_helper(wmr, start_path = None, parent_view = None):
    from Qt import QtWidgets

    if start_path is None:
        start_path = []

    vc = ViewCollector()
    vc.set_start_path(start_path)
    newtw = WaNoTreeWalker(wmr)

    # Stage 3.5: Set Root Model
    vc.set_wano_model_root(wmr.get_root())
    newtw.walker(capture=False, path_visitor_function=None, subdict_visitor_function=vc.root_setter_subdict,
                 data_visitor_function=vc.root_setter_data)

    # Stage 1: Construct all views
    newtw.walker(capture=False, path_visitor_function=None, subdict_visitor_function=vc.assemble_views,
                 data_visitor_function=vc.data_visitor_view_assembler)

    views_by_path = vc.get_views_by_path()

    # Stage 2: Set all model paths
    newtw.walker(capture=False, path_visitor_function=None, subdict_visitor_function=vc.path_setter_subdict,
                 data_visitor_function=vc.path_setter_data)

    # Stage 2: Parent all models
    newtw.walker(capture=False, path_visitor_function=None, subdict_visitor_function=vc.assemble_model_parenter,
                 data_visitor_function=vc.data_visitor_model_parenter)

    # Stage 2: Parent all views
    newtw.walker(capture=False, path_visitor_function=None, subdict_visitor_function=vc.assemble_views_parenter,
                 data_visitor_function=vc.data_visitor_view_parenter)

    # Stage 3 (or Stage 0): Initialize the rootview parent
    rootview = vc.get_views_by_path()[()]
    if parent_view is None:
        anonymous_parent = QtWidgets.QWidget()
    else:
        anonymous_parent = parent_view
    rootview.set_parent(anonymous_parent)

    # Stage 4: Put actual data into the views from the ones deep in the hierarchy to the shallow ones
    sorted_paths = [*reversed(sorted(views_by_path.keys(), key=len))]
    for path in sorted_paths:
        views_by_path[path].init_from_model()

    rootview.init_from_model()

    # Stage 5: Update the layout
    #anonymous_parent.update()
    return wmr,rootview


def wano_constructor(wano: WaNoListEntry):
    # Timo: Begin path, Begin parse, etc. in the function above. Then call the function above
    # and make this the main entry point
    wano_dir_root = wano.folder
    xml = get_wano_xml_path(wano.folder, wano_name_override=wano.name)
    from SimStackServer.WaNo.WaNoModels import WaNoModelRoot
    from WaNo.view.WaNoViews import WanoQtViewRoot
    # MODELROOTDIRECT
    wmr = WaNoModelRoot(wano_dir_root=wano_dir_root, explicit_xml=xml)
    wmr.set_view_class(WanoQtViewRoot)
    wmr, rootview = wano_constructor_helper(wmr)
    return wmr, rootview


class WaNoFactory(object):
    @classmethod
    def get_model_class(cls, name):
        from SimStackServer.WaNo.WaNoModels import WaNoItemFloatModel, WaNoModelListLike, \
            WaNoItemStringModel, WaNoItemBoolModel, WaNoModelDictLike, WaNoChoiceModel, \
            MultipleOfModel, WaNoItemFileModel, WaNoItemIntModel, WaNoItemScriptFileModel, \
            WaNoMatrixModel, WaNoThreeRandomLetters, WaNoSwitchModel, WaNoDynamicChoiceModel, \
            WaNoNoneModel

        wano_list = {  # kwargs['xml'] = self.full_xml.find("WaNoRoot")
            "WaNoFloat": WaNoItemFloatModel,
            "WaNoMatrixFloat": WaNoMatrixModel,
            "WaNoMatrixString": WaNoMatrixModel,
            "WaNoInt": WaNoItemIntModel,
            "WaNoString": WaNoItemStringModel,
            "WaNoListBox": WaNoModelListLike,
            "WaNoBox": WaNoModelDictLike,
            "WaNoDictBox": WaNoModelDictLike,
            "WaNoInviBox": WaNoModelDictLike,
            "WaNoSwitch": WaNoSwitchModel,
            "WaNoGroup": WaNoModelDictLike,
            "WaNoBool": WaNoItemBoolModel,
            "WaNoFile": WaNoItemFileModel,
            "WaNoChoice": WaNoChoiceModel,
            "WaNoDropDown": WaNoChoiceModel,
            "WaNoMultipleOf": MultipleOfModel,
            "WaNoScript": WaNoItemScriptFileModel,
            "WaNoDynamicDropDown": WaNoDynamicChoiceModel,
            "WaNoTabs": WaNoModelDictLike,
            "WaNone": WaNoNoneModel,
            "WaNoThreeRandomLetters": WaNoThreeRandomLetters
        }
        return wano_list[name]

    @classmethod
    def get_qt_view_class(cls, name):
        from SimStackServer.WaNo.WaNoModels import WaNoItemFloatModel, WaNoModelListLike, \
            WaNoItemStringModel, WaNoItemBoolModel, WaNoModelDictLike, WaNoChoiceModel, \
            MultipleOfModel, WaNoItemFileModel, WaNoItemIntModel, WaNoItemScriptFileModel, \
            WaNoMatrixModel, WaNoThreeRandomLetters, WaNoSwitchModel, WaNoDynamicChoiceModel, \
            WaNoNoneModel
        try:
            from WaNo.view.WaNoViews import WaNoItemFloatView, WaNoBoxView, WaNoItemStringView, \
                WaNoItemBoolView, WaNoItemFileView, WaNoChoiceView, MultipleOfView, WaNoItemIntView, \
                WaNoTabView, WaNoGroupView, WaNoScriptView, WaNoDropDownView, WaNoMatrixFloatView, WaNoMatrixStringView, \
                WaNoSwitchView, WaNoInvisibleBoxView, WaNoNone
        except ImportError as e:
            #Workaround to make this work from within SimStackServer
            return None

        wano_list = {  # kwargs['xml'] = self.full_xml.find("WaNoRoot")
            "WaNoFloat": (WaNoItemFloatModel, WaNoItemFloatView),
            "WaNoMatrixFloat": (WaNoMatrixModel, WaNoMatrixFloatView),
            "WaNoMatrixString": (WaNoMatrixModel, WaNoMatrixStringView),
            "WaNoInt": (WaNoItemIntModel, WaNoItemIntView),
            "WaNoString": (WaNoItemStringModel, WaNoItemStringView),
            "WaNoListBox": (WaNoModelListLike, WaNoBoxView),
            "WaNoBox": (WaNoModelDictLike, WaNoBoxView),
            "WaNoDictBox": (WaNoModelDictLike, WaNoBoxView),
            "WaNoInviBox": (WaNoModelDictLike, WaNoInvisibleBoxView),
            "WaNoSwitch": (WaNoSwitchModel, WaNoSwitchView),
            "WaNoGroup": (WaNoModelDictLike, WaNoGroupView),
            "WaNoBool": (WaNoItemBoolModel, WaNoItemBoolView),
            "WaNoFile": (WaNoItemFileModel, WaNoItemFileView),
            "WaNoChoice": (WaNoChoiceModel, WaNoChoiceView),
            "WaNoDropDown": (WaNoChoiceModel, WaNoDropDownView),
            "WaNoMultipleOf": (MultipleOfModel, MultipleOfView),
            "WaNoScript": (WaNoItemScriptFileModel, WaNoScriptView),
            "WaNoDynamicDropDown": (WaNoDynamicChoiceModel, WaNoDropDownView),
            "WaNoTabs": (WaNoModelDictLike, WaNoTabView),
            "WaNone": (WaNoNoneModel, WaNoNone),
            "WaNoThreeRandomLetters": (WaNoThreeRandomLetters, WaNoItemStringView)
        }
        return wano_list[name][1]

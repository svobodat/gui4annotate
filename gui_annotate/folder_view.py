#!/usr/bin/env python3
import functools

from gi.repository import Gtk, GObject, Gdk
import os
from gui_annotate.vec import Vec2D
from gui_annotate.constants import Constants


class SimpleTree:
    def __init__(self, parent=None, data=None):
        self.parent = parent
        self.children = []
        self.data = data
        if parent is not None:
            self.parent.children.append(self)


class FolderStore(Gtk.TreeStore):
    def __init__(self, *args, **kwargs):
        Gtk.TreeStore.__init__(self, *args, **kwargs)

        self.roi_data = None

    def set_tree(self, tree):
        self.roi_data = tree

    def append_custom(self, type, full_path=None, parent=None, roi_data=None, change=False):
        if type is Constants.FOLDER:
            if full_path is None:
                raise ValueError('You need to specify path for folder')
            small_path = os.path.split(full_path)[1]
            tree_iter = self.append(None if parent is None else parent.data['iter'],
                                    (None, False, Constants.DEFAULT_TEXT_COLOR, Constants.FOLDER_ICON, small_path, '', '','', ''))
            tree = SimpleTree(parent=parent, data={'type': Constants.FOLDER, 'iter': tree_iter, 'full_path': full_path, 'changed': False})
            self.set_value(tree_iter, 0, tree)
            return tree
        if type is Constants.FILE:
            if full_path is None:
                raise ValueError('You need to specify path for file')
            if os.path.splitext(full_path)[1].lower() not in Constants.IMAGE_EXT:
                return None
            small_path = os.path.split(full_path)[1]
            tree_iter = self.append(None if parent is None else parent.data['iter'],
                                    (None, False, Constants.DEFAULT_TEXT_COLOR, Constants.FILE_ICON, small_path, '<b>0</b>', '', '', ''))
            tree = SimpleTree(parent=parent, data={'type': Constants.FILE, 'iter': tree_iter, 'full_path': full_path, 'changed': False, 'ROIS': 0})
            txt_file = os.path.splitext(full_path)[0] + '.txt'
            if os.path.isfile(txt_file):
                with open(txt_file, mode='r') as f:
                    for line in f.readlines():
                        self.append_custom(Constants.ROI, parent=tree, roi_data=line.strip())
            self.set_value(tree_iter, 0, tree)
            return tree
        if type is Constants.ROI:
            data = roi_data.split(',')
            roi_f = tuple(map(float, data[0:4]))
            roi_s = tuple(map(lambda x: '%.1f' % x, roi_f))
            name = data[-1]
            tree_iter = self.append(None if parent is None else parent.data['iter'],
                                    (None, True, Constants.DEFAULT_TEXT_COLOR, Constants.ROI_ICON, name, roi_s[0], roi_s[1], roi_s[2], roi_s[3]))
            tree = SimpleTree(parent=parent, data={'type':Constants.ROI, 'iter':tree_iter, 'class': name, 'lt': Vec2D(roi_f[0], roi_f[1]), 'rb': Vec2D(roi_f[2], roi_f[3]), 'changed':False})
            self.set_value(parent.data['iter'], 5, '<b>' + str(len(parent.children)) + '</b>')
            parent.data['ROIS'] = len(tree.children)
            self.set_value(tree_iter, 0, tree)
            if change:
                change_tree = tree
                while change_tree is not None:
                    self.set_value(change_tree.data['iter'], 2, Constants.UNSAVED_TEXT_COLOR)
                    change_tree.data['changed'] = True
                    change_tree = change_tree.parent
            return tree

    def delete_roi(self, roi):
        parent = roi.parent
        parent.children.remove(roi)
        self.remove(roi.data['iter'])
        self.set_value(parent.data['iter'], 5, '<b>' + str(len(parent.children)) + '</b>')

        change_tree = parent
        while change_tree is not None:
            self.set_value(change_tree.data['iter'], 2, Constants.UNSAVED_TEXT_COLOR)
            change_tree.data['changed'] = True
            change_tree = change_tree.parent

    def save_handler(self, w, save_all, parent):
        if save_all:
            self.save(self.roi_data)
            w.can_save_all = False
            parent.area.can_save = False
        else:
            self.save(parent.current_node)
            if not self.any_unsaved(self.roi_data):
                w.can_save_all = False
                parent.area.can_save = False
        w.can_save = False
        parent.area.can_save = False

    def save(self, node):
        if node.data['type'] == Constants.FOLDER:
            for child in node.children:
                self.save(child)
            self.set_value(node.data['iter'], 2, Constants.DEFAULT_TEXT_COLOR)
            node.data['changed'] = False
        if node.data['type'] == Constants.FILE and node.data['changed']:
            save_string = functools.reduce(lambda x, y: x + str(y.data['lt']) + ',' + str(y.data['rb']) + ',' + y.data['class'] + os.linesep, node.children, '')
            for child in node.children:
                self.set_value(child.data['iter'], 2, Constants.DEFAULT_TEXT_COLOR)
                child.data['changed'] = False
            txt_file = os.path.splitext(node.data['full_path'])[0] + '.txt'
            if save_string is not '':
                with open(txt_file, mode='w') as f:
                    f.write(save_string)
            else:
                if os.path.isfile(txt_file):
                    os.remove(txt_file)
            self.set_value(node.data['iter'], 2, Constants.DEFAULT_TEXT_COLOR)
            node.data['changed'] = False
            parent = node.parent
            while parent is not None:
                if self.any_unsaved(parent):
                    break
                self.set_value(parent.data['iter'], 2, Constants.DEFAULT_TEXT_COLOR)
                parent.data['changed'] = False
                parent = parent.parent

    def any_unsaved(self, node):
        return any([child.data['changed'] for child in node.children])



class FolderView(Gtk.ScrolledWindow):
    folder = GObject.property(type=str, default=None, flags=GObject.PARAM_READWRITE)
    current_im_node = GObject.property(type=GObject.TYPE_PYOBJECT, flags=GObject.PARAM_READWRITE)

    def __init__(self, *args, **kwargs):
        Gtk.ScrolledWindow.__init__(self, *args, **kwargs)
        self.tree_view = Gtk.TreeView()
        self.data = FolderStore(*Constants.FOLDER_VIEW_ROW)
        self.tree_view.set_model(self.data)
        self.tree_view.connect('row-activated', self.selected_row)

        self.connect('notify::folder', lambda view, _: [None, self.data.clear(), self.data.set_tree(self.data.append_custom(Constants.FOLDER, full_path=self.folder)), self.set_folder(self.folder,self.data.roi_data)][0])

        icon = Gtk.CellRendererPixbuf.new()
        icon_column = Gtk.TreeViewColumn.new()
        icon_column.pack_start(icon, True)
        icon_column.add_attribute(icon, 'icon_name', 3)
        self.tree_view.append_column(icon_column)

        name = Gtk.CellRendererText.new()
        name_column = Gtk.TreeViewColumn.new()
        name_column.pack_start(name, True)
        name_column.add_attribute(name, 'text', 4)
        name_column.add_attribute(name, 'editable', 1)
        name_column.add_attribute(name, 'foreground-rgba', 2)
        self.tree_view.append_column(name_column)

        for i in range(5, 9):
            roi_data = Gtk.CellRendererText.new()
            roi_data_column = Gtk.TreeViewColumn.new()
            roi_data_column.pack_start(roi_data, True)
            roi_data_column.add_attribute(roi_data, 'markup', i)
            roi_data_column.add_attribute(roi_data, 'editable', 1)
            roi_data_column.add_attribute(roi_data, 'foreground-rgba', 2)
            self.tree_view.append_column(roi_data_column)

        self.tree_view.set_headers_visible(False)

        self.add(self.tree_view)
        self.set_size_request(500, 612)
        self.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)

    def set_folder(self, path, parent):
        all_files = sorted([os.path.join(path, f) for f in os.listdir(path)])
        dirs = [d for d in all_files if os.path.isdir(d)]
        files = [f for f in all_files if os.path.isfile(f)]

        for d in dirs:
            self.set_folder(d, self.data.append_custom(Constants.FOLDER, full_path=d, parent=parent))

        for f in files:
            self.data.append_custom(Constants.FILE, full_path=f, parent=parent)

    def selected_row(self, tree, path, _):
        row = tree.get_model()[path]
        node = row[0]
        if node.data['type'] == Constants.FILE:
            self.set_property('current_im_node', node)
            self.tree_view.expand_row(path, False)
        if node.data['type'] == Constants.FOLDER:
            if not self.tree_view.row_expanded(path):
                self.tree_view.expand_row(path, False)
            else:
                self.tree_view.collapse_row(path)
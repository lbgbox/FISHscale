import sys
from PyQt5.QtWidgets import (QPushButton, QDialog, QTreeWidget,
                             QTreeWidgetItem, QVBoxLayout,
                             QHBoxLayout, QFrame, QLabel,
                             QApplication,QListWidget,QScrollBar)

from PyQt5.QtWidgets import * 
from PyQt5 import QtWidgets
from PyQt5 import QtCore, QtGui 
from PyQt5.QtGui import * 
from PyQt5.QtCore import * 
import sys 
try:
    import open3d as o3d
except:
    pass
import pandas as pd
import numpy as np
import random
import time
import FISHscale


class Window: 

    def __init__(self,dataset,columns,width=2000,height=2000,show_axis=False,color_dic={}): 
        
        super().__init__() 
        
        """
        GUI for Open3D Make Plots Fast Again
        
        dataframe: Pass the pandas dataframe, column names must be 'c_px_microscope_stitched','r_px_microscope_stitched' and gene
        color_dic: pass dictionary of desired color in RGB for each unique gene in the parquet_file
        
        """
        self.dataset = dataset

        # setting title 
        if str(self.dataset.__class__) == str(FISHscale.utils.dataset.Dataset):
            print('Single Dataset')
            self.offset = np.array([self.dataset.x_offset, self.dataset.y_offset, self.dataset.z_offset])
            self.color_dic = color_dic
            self.dic_pointclouds ={self.dataset.gene_label:self.pass_data()}
            self.dic_pointclouds['File'] = [str(self.dataset.filename)]
            print('Data Loaded')

        elif str(self.dataset.__class__) == str(FISHscale.utils.dataset.MultiDataset):
            print('MultiDataset')
            self.x_label,self.y_label = self.dataset.x_label, self.dataset.y_label
            self.color_dic = color_dic
            self.dic_pointclouds ={self.dataset.gene_label:self.pass_multi_data()}
            self.dic_pointclouds['File'] = []
            for x in self.dataset:
                self.dic_pointclouds['File'].append(str(x.filename))
            print('Data Loaded')

        self.show_axis= show_axis
        self.vis = Visualizer(self.dic_pointclouds, columns, width=2000, height=2000, show_axis=self.show_axis, color_dic=None)
        self.collapse = CollapsibleDialog(self.dic_pointclouds,vis=self.vis)
        self.widget_lists = self.collapse.widget_lists
        self.collapse.show()
        
        for l in self.widget_lists:
            if l.section == 'File':
                l.list_widget.itemSelectionChanged.connect(l.selectionChanged)
                l.list_widget.itemSelectionChanged.connect(self.collapse.possible)
            else:
                l.list_widget.itemSelectionChanged.connect(l.selectionChanged)

        self.vis.execute()

    def pass_data(self):
        r = lambda: random.randint(0,255)

        dic_coords = {}
        for gene,x,y in self.dataset.xy_groupby_gene_generator():
            coords = np.vstack([x,y,np.zeros(x.shape[0])]).T
            coords = coords + self.offset

            if self.color_dic[gene]:
                col = np.array([self.color_dic[gene]]*coords.shape[0])/255
            else:
                col = [(r(),r(),r())]
                self.color_dic[gene] = col
                col = np.array(col*coords.shape[0])/255 
            dic_coords[str(gene)] = (coords,col,np.array([self.name]*coords.shape[0]))
        return dic_coords


    def pass_multi_data(self):
        r = lambda: random.randint(0,255)
        dic_coords = {}
        for dataframe in self.dataset:
            print(dataframe.filename)

            offset = np.array([dataframe.x_offset, dataframe.y_offset, dataframe.z_offset])
            for gene,x,y in dataframe.xy_groupby_gene_generator():

                coords = np.vstack([x,y,np.zeros(x.shape[0])]).T
                coords = coords + offset

                if str(gene) in self.color_dic:
                    col = np.array([self.color_dic[gene]]*coords.shape[0])/255
                else:
                    col = [(r(),r(),r())]
                    self.color_dic[gene] = col
                    col = np.array(col*coords.shape[0])/255 

                if str(gene) not in dic_coords:
                    dic_coords[str(gene)] = (coords,col,np.array([dataframe.filename]*coords.shape[0]))

                else:
                    c1,col1,n1 = dic_coords[str(gene)]
                    print('col1',col1.shape,'col',col.shape)
                    col = col[:,0,:]

                    name = np.concatenate([n1,np.array([dataframe.filename]*coords.shape[0])])
                    coords = np.concatenate([c1,coords])
                    col = np.concatenate([col1,col])
                    dic_coords[str(gene)] = (coords,col,name)

        return dic_coords

    
class Visualizer:
    def __init__(self,dic_pointclouds,columns,width=2000,height=2000,show_axis=False,color_dic=None):
        
        self.visM = o3d.visualization.Visualizer()
        self.visM.create_window(height=height,width=width,top=0,left=500)
        
        self.dic_pointclouds= dic_pointclouds
        
        self.allgenes = np.concatenate([self.dic_pointclouds[columns[0]][i][0] for i in self.dic_pointclouds[columns[0]].keys()])
        
        self.allcolors = np.concatenate([self.dic_pointclouds[columns[0]][i][1] for i in self.dic_pointclouds[columns[0]].keys()])

        self.pcd = o3d.geometry.PointCloud()
        self.pcd.points = o3d.utility.Vector3dVector(self.allgenes)
        self.pcd.colors = o3d.utility.Vector3dVector(self.allcolors)   
        self.visM.add_geometry(self.pcd)
        opt = self.visM.get_render_option()
        if show_axis:
            opt.show_coordinate_frame = True
        opt.background_color = np.asarray([0, 0, 0])
    
    def execute(self):
        self.visM.run()
        self.visM.destroy_window()
        
        

class SectionExpandButton(QPushButton):
    """a QPushbutton that can expand or collapse its section
    """
    def __init__(self, item, text = "", parent = None):
        super().__init__(text, parent)
        self.section = item
        self.clicked.connect(self.on_clicked)

    def on_clicked(self):
        """toggle expand/collapse of section by clicking
        """
        if self.section.isExpanded():
            self.section.setExpanded(False)
        else:
            self.section.setExpanded(True)    
            
class ListWidget(QWidget):
    def __init__(self,subdic,section,vis):
        super().__init__()
        
        # creating a QListWidget 
        self.list_widget = QListWidget()
        
        # scroll bar 
        self.subdic = subdic
        self.section = section
        self.selected = False
        self.vis = vis
        scroll_bar = QScrollBar() 
        # setting style sheet to the scroll bar 
        scroll_bar.setStyleSheet("background : black;") 
        # adding extra scroll bar to it 
        self.list_widget.addScrollBarWidget(scroll_bar, Qt.AlignLeft)
        self.add_items()

        self.list_widget.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.tissue_selected = [x for x in self.vis.dic_pointclouds['File']]

    def add_items(self):
        for e in self.subdic:
            i = QListWidgetItem(str(e)) 
            
            try:
                i.setBackground(QColor(c[0],c[1],c[2],120))
                c = self.subdic[e][1][0,:]*255
            except:
                pass
            self.list_widget.addItem(i)
        # adding items to the list widget '''
        
    def selectionChanged(self):
        self.selected = [i.text() for i in self.list_widget.selectedItems()]
        if self.selected[0] in self.vis.dic_pointclouds['File'] and self.section == 'File':
            self.tissue_selected = [x for x in self.selected if x in self.vis.dic_pointclouds['File']]
            tissue_loop = True

        else:
            tissue_loop = False

        if not tissue_loop:
            genes = []
            points, colors,filenames = [], [],[]

            for i in self.selected:

                ps,cs,filename = self.vis.dic_pointclouds[self.section][i]
                points.append(ps)
                colors.append(cs)
                filenames.append(filename)

            ps,cs = np.concatenate(points), np.concatenate(colors)
            filenames = np.concatenate(filenames)
            tissue_filter = np.isin(filenames,self.tissue_selected)
            ps = ps[tissue_filter,:]
            cs = cs[tissue_filter,:]
            self.vis.pcd.points = o3d.utility.Vector3dVector(ps)
            self.vis.pcd.colors = o3d.utility.Vector3dVector(cs)
            self.vis.visM.update_geometry(self.vis.pcd)
            self.vis.visM.poll_events()
            self.vis.visM.update_renderer()
    

class CollapsibleDialog(QDialog):
    """a dialog to which collapsible sections can be added;
    subclass and reimplement define_section() to define sections and
        add them as (title, widget) tuples to self.sections
    """
    def __init__(self,dic,vis):
        super().__init__()
        self.tree = QTreeWidget()
        #self.tree.setSelectionMode(QtWidgets.QAbstractItemView.MultiSelection)

        self.tree.setHeaderHidden(True)
        self.vis = vis
        layout = QVBoxLayout()
        layout.addWidget(self.tree)
        self.setLayout(layout)
        self.setGeometry(100, 100, 200, 800) 
        self.tree.setIndentation(0)
        self.dic = dic
        
        self.widget_lists = []
        self.sections = {}

        for x in self.dic:
            self.define_section(x)
            
        self.add_sections()

    def possible(self):
        for x in self.widget_lists:
            if x.section == 'File':
                ts = x.tissue_selected
        for x in self.widget_lists:
            if x.section != 'File':
                x.tissue_selected = ts

        
    def add_sections(self):
        """adds a collapsible sections for every 
        (title, widget) tuple in self.sections
        """
        for title in self.sections:
            widget = self.sections[title]
            button1 = self.add_button(title)
            section1 = self.add_widget(button1, widget)
            button1.addChild(section1)       

    def define_section(self,title):
        """reimplement this to define all your sections
        and add them as (title, widget) tuples to self.sections
        """
        widget = QFrame(self.tree)
        layout = QHBoxLayout(widget)

        #layout.addWidget(QLabel("Bla"))
        lw = ListWidget(self.dic[title],title,self.vis)
        list_widget = lw.list_widget
        layout.addWidget(list_widget)
        self.sections[title]= widget
        self.widget_lists.append(lw)
        
    def add_button(self, title):
        """creates a QTreeWidgetItem containing a button 
        to expand or collapse its section
        """
        item = QTreeWidgetItem()
        self.tree.addTopLevelItem(item)
        self.tree.setItemWidget(item, 0, SectionExpandButton(item, text = title))
        return item

    def add_widget(self, button, widget):
        """creates a QWidgetItem containing the widget,
        as child of the button-QWidgetItem
        """
        section = QTreeWidgetItem(button)
        section.setDisabled(True)
        self.tree.setItemWidget(section, 0, widget)
        return section
        

        
        


"""
@package rdigit.toolbars

@brief rdigit toolbars and icons.

Classes:
 - toolbars::RDigitToolbar
 
(C) 2014 by the GRASS Development Team
This program is free software under the GNU General Public
License (>=v2). Read the file COPYING that comes with GRASS
for details.

@author Anna Petrasova <kratochanna gmail.com>
"""

import wx

from core.utils import _
from gui_core.toolbars import BaseToolbar
from icons.icon import MetaIcon
from gui_core.widgets import FloatValidator


rdigitIcons = {'area': MetaIcon(img='polygon-create',
                                label=_('Digitize area')),
               'line': MetaIcon(img='line-create',
                                label=_('Digitize line')),
               'point': MetaIcon(img='point-create',
                                 label=_('Digitize point')),
               'quit': MetaIcon(img='quit', label=_("Quit raster digitizer"))}


class RDigitToolbar(BaseToolbar):
    """IClass Map toolbar
    """
    def __init__(self, parent, controller, toolSwitcher):
        """IClass Map toolbar constructor
        """
        BaseToolbar.__init__(self, parent, toolSwitcher)
        self._controller = controller
        self.InitToolbar(self._toolbarData())

        self._mapSelectionComboId = wx.NewId()
        self._mapSelectionCombo = wx.ComboBox(self, id=self._mapSelectionComboId,
                                              value=_("Select raster map"),
                                              choices=[], size=(120, -1))
        self._mapSelectionCombo.Bind(wx.EVT_COMBOBOX, self.OnMapSelection)
        self._mapSelectionCombo.SetEditable(False)
        self.InsertControl(0, self._mapSelectionCombo)
        self._previousMap = self._mapSelectionCombo.GetValue()

        self._cellValues = set(['1'])
        self._valueComboId = wx.NewId()
        # validator does not work with combobox, SetBackgroundColor is not working
        self._valueCombo = wx.ComboBox(self, id=self._valueComboId,
                                       choices=list(self._cellValues), size=(80, -1),
                                       validator=FloatValidator())
        self._valueCombo.Bind(wx.EVT_COMBOBOX, lambda evt: self._cellValueChanged())
        self._valueCombo.Bind(wx.EVT_TEXT, lambda evt: self._cellValueChanged())
        self._valueCombo.SetSelection(0)
        self._cellValueChanged()
        self.InsertControl(5, wx.StaticText(self, label=" %s" % _("Cell value:")))
        self.InsertControl(6, self._valueCombo)

        self._widthValueId = wx.NewId()
        # validator does not work with combobox, SetBackgroundColor is not working
        self._widthValue = wx.TextCtrl(self, id=self._widthValueId, value='0',
                                       size=(80, -1), validator=FloatValidator())
        self._widthValue.Bind(wx.EVT_TEXT, lambda evt: self._widthValueChanged())
        self._widthValueChanged()
        self._widthValue.SetToolTipString(_("Width of currently digitized line/point in map units."))
        self.InsertControl(7, wx.StaticText(self, label=" %s" % _("Width:")))
        self.InsertControl(8, self._widthValue)

        for tool in (self.area, self.line, self.point):
            self.toolSwitcher.AddToolToGroup(group='mouseUse', toolbar=self, tool=tool)
        self._default = self.area
        # realize the toolbar
        self.Realize()

    def _toolbarData(self):
        """Toolbar data"""
        return self._getToolbarData((('area', rdigitIcons['area'],
                                      lambda event: self._controller.SelectType('area'),
                                      wx.ITEM_CHECK),
                                     ('line', rdigitIcons['line'],
                                      lambda event: self._controller.SelectType('line'),
                                      wx.ITEM_CHECK),
                                     ('point', rdigitIcons['point'],
                                      lambda event: self._controller.SelectType('point'),
                                      wx.ITEM_CHECK),
                                     (None, ),
                                     (None, ),
                                     ('quit', rdigitIcons['quit'],
                                      lambda event: self.parent.QuitRDigit())))

    def UpdateRasterLayers(self, rasters):
        new = _("New raster map")
        items = [raster.name for raster in rasters if raster.name is not None]
        items.insert(0, new)
        self._mapSelectionCombo.SetItems(items)

    def OnMapSelection(self, event):
        """!Either map to edit or create new map selected."""
        idx = self._mapSelectionCombo.GetSelection()
        if idx == 0:
            ret = self._controller.SelectNewMap()
        else:
            ret = self._controller.SelectOldMap(self._mapSelectionCombo.GetString(idx))
        if not ret:
            # in wxpython 3 we can't set value which is not in the items
            # when not editable
            self._mapSelectionCombo.SetEditable(True)
            self._mapSelectionCombo.SetValue(self._previousMap)
            self._mapSelectionCombo.SetEditable(False)
        # we need to get back to previous
        self._previousMap = self._mapSelectionCombo.GetValue()

    def NewRasterAdded(self, name):
        idx = self._mapSelectionCombo.Append(name)
        self._mapSelectionCombo.SetSelection(idx)

    def UpdateCellValues(self, values=None):
        if not values:
            values = [self._valueCombo.GetValue()]
        for value in values:
            self._cellValues.add(str(value))

        valList = sorted(list(self._cellValues), key=float)
        self._valueCombo.SetItems(valList)

    def _cellValueChanged(self):
        value = self._valueCombo.GetValue()
        try:
            value = float(value)
            self._controller.SetCellValue(value)
        except ValueError:
            return

    def _widthValueChanged(self):
        value = self._widthValue.GetValue()
        try:
            value = float(value)
            self._controller.SetWidthValue(value)
        except ValueError:
            self._controller.SetWidthValue(0)
            return
            
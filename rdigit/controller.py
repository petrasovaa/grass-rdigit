# -*- coding: utf-8 -*-
import os
import tempfile
import wx

from grass.script import core as gcore
from grass.script import raster as grast
from grass.exceptions import CalledModuleError
from grass.pydispatch.signal import Signal

from core.gcmd import GError, GMessage
from rdigit.dialogs import NewRasterDialog


class RDigitController:
    def __init__(self, giface, mapWindow):
        self._giface = giface
        self._mapWindow = mapWindow

        self._editedRaster = None
        self._areas = None
        self._lines = None
        self._points = None
        self._all = []
        self._drawing = False
        self._graphicsType = 'area'
        self._currentCellValue = None
        self._currentWidthValue = None
        self._catCount = 1
        self._catToCellValue = {}
        self._catToWidthValue = {}

        self._oldMouseUse = None
        self._oldCursor = None

        self.newRasterCreated = Signal('RDigitController:newRasterCreated')
        self.newFeatureCreated = Signal('RDigitController:newFeatureCreated')

    def _connectAll(self):
        self._mapWindow.mouseLeftDown.connect(self._start)
        self._mapWindow.mouseLeftUp.connect(self._addPoint)
        self._mapWindow.mouseRightUp.connect(self._finish)
        self._mapWindow.Unbind(wx.EVT_CONTEXT_MENU)

    def _disconnectAll(self):
        self._mapWindow.mouseLeftDown.disconnect(self._start)
        self._mapWindow.mouseLeftUp.disconnect(self._addPoint)
        self._mapWindow.mouseRightUp.connect(self._finish)
        self._mapWindow.Bind(wx.EVT_CONTEXT_MENU, self._mapWindow.OnContextMenu)

    def _start(self, x, y):
        if not self._editedRaster:
            GMessage(parent=self._mapWindow, message=_("Please select first the raster map"))
            return
        if not self._drawing:
            if self._graphicsType == 'area':
                item = self._areas.AddItem(coords=[])
                item.SetPropertyVal('penName', 'pen1')
                self._all.append(item)
            elif self._graphicsType == 'line':
                item = self._lines.AddItem(coords=[])
                item.SetPropertyVal('penName', 'pen1')
                self._all.append(item)
            elif self._graphicsType == 'point':
                item = self._points.AddItem(coords=[])
                item.SetPropertyVal('penName', 'pen1')
                self._all.append(item)
            self._drawing = True

    def _addPoint(self, x, y):
        if not self._drawing:
            return

        if self._graphicsType == 'area':
            area = self._areas.GetItem(-1)
            coords = area.GetCoords() + [[x, y]]
            area.SetCoords(coords)
        elif self._graphicsType == 'line':
            line = self._lines.GetItem(-1)
            coords = line.GetCoords() + [[x, y]]
            line.SetCoords(coords)
        elif self._graphicsType == 'point':
            point = self._points.GetItem(-1)
            point.SetCoords([x, y])
            self._finish(x, y)
        # draw
        self._mapWindow.ClearLines()
        self._areas.Draw(pdc=self._mapWindow.pdcTmp)
        self._lines.Draw(pdc=self._mapWindow.pdcTmp)
        self._mapWindow.Refresh()

    def _finish(self, x, y):
        if self._graphicsType == 'point':
            item = self._points.GetItem(-1)
        elif self._graphicsType == 'area':
            item = self._areas.GetItem(-1)
        elif self._graphicsType == 'line':
            item = self._lines.GetItem(-1)

        self._drawing = False
        item.SetPropertyVal('brushName', 'done')
        item.AddProperty('cat')
        item.AddProperty('cellValue')
        item.AddProperty('widthValue')
        item.SetPropertyVal('cellValue', self._currentCellValue)
        item.SetPropertyVal('cat', self._catCount)
        item.SetPropertyVal('widthValue', self._currentWidthValue)
        self._catCount += 1
        self.newFeatureCreated.emit()

        self._points.Draw(pdc=self._mapWindow.pdcTmp)
        self._areas.Draw(pdc=self._mapWindow.pdcTmp)
        self._lines.Draw(pdc=self._mapWindow.pdcTmp)

        self._mapWindow.Refresh()

    def SelectType(self, drawingType):
        self._graphicsType = drawingType

    def SetCellValue(self, value):
        self._currentCellValue = value

    def SetWidthValue(self, value):
        self._currentWidthValue = value

    def Start(self):
        """register graphics to map window,
        connect required mouse signals.
        """
        self._oldMouseUse = self._mapWindow.mouse['use']
        self._oldCursor = self._mapWindow.GetNamedCursor()

        self._connectAll()

        # change mouse['box'] and pen to draw line during dragging
        # TODO: better solution for drawing this line
        self._mapWindow.mouse['use'] = None
        self._mapWindow.mouse['box'] = "line"
        self._mapWindow.pen = wx.Pen(colour='red', width=2, style=wx.SHORT_DASH)
#
        self._areas = self._mapWindow.RegisterGraphicsToDraw(graphicsType='polygon',
                                                             mapCoords=True)
        self._areas.AddPen('pen1', wx.Pen(colour=wx.Colour(0, 255, 0, 100), width=2, style=wx.SOLID))
        self._areas.AddBrush('done', wx.Brush(colour=wx.Colour(0, 255, 0, 100), style=wx.SOLID))

        self._lines = self._mapWindow.RegisterGraphicsToDraw(graphicsType='line',
                                                             mapCoords=True)
        self._lines.AddPen('pen1', wx.Pen(colour=wx.Colour(0, 255, 0, 100), width=2, style=wx.SOLID))
        self._lines.AddBrush('done', wx.Brush(colour=wx.Colour(0, 255, 0, 100), style=wx.SOLID))

        self._points = self._mapWindow.RegisterGraphicsToDraw(graphicsType='point',
                                                              mapCoords=True)
        self._points.AddPen('pen1', wx.Pen(colour=wx.Colour(0, 255, 0, 100), width=2, style=wx.SOLID))
        self._points.AddBrush('done', wx.Brush(colour=wx.Colour(0, 255, 0, 100), style=wx.SOLID))

        # change the cursor
        self._mapWindow.SetNamedCursor('pencil')

    def Stop(self, restore=True):
        """
        :param restore: if restore previous cursor, mouse['use']
        """
        self._exportRaster()
        self._mapWindow.ClearLines(pdc=self._mapWindow.pdcTmp)
        self._mapWindow.mouse['end'] = self._mapWindow.mouse['begin']
        # disconnect mouse events
        self._disconnectAll()
        # unregister
        self._mapWindow.UnregisterGraphicsToDraw(self._areas)
        self._mapWindow.UnregisterGraphicsToDraw(self._lines)
        self._mapWindow.UnregisterGraphicsToDraw(self._points)
        #self._registeredGraphics = None
        self._mapWindow.UpdateMap(render=False)

        if restore:
            # restore mouse['use'] and cursor to the state before measuring starts
            self._mapWindow.SetNamedCursor(self._oldCursor)
            self._mapWindow.mouse['use'] = self._oldMouseUse

    def SelectOldMap(self, name):
        self._editedRaster = name

    def SelectNewMap(self):
        dlg = NewRasterDialog(parent=self._mapWindow)
        if dlg.ShowModal() == wx.ID_OK:
            self._createNewMap(mapName=dlg.GetMapName(), mapType=dlg.GetMapType())
        dlg.Destroy()

    def _createNewMap(self, mapName, mapType):
        name = mapName.split('@')[0]
        types = {'CELL': 'int', 'FCELL': 'float', 'DCELL': 'double'}
        try:
            grast.mapcalc(exp="{name} = {mtype}(null())".format(name=name, mtype=types[mapType]),
                          overwrite=True, quiet=True)
        except CalledModuleError:
            GError(parent=self._mapWindow, message=_("Failed to create new raster map"))
            return
        name = name + '@' + gcore.gisenv()['MAPSET']
        self._editedRaster = name
        self.newRasterCreated.emit(name=name)

    def _exportRaster(self):
        if not self._editedRaster:
            return

        asciiFile = tempfile.NamedTemporaryFile(delete=False)
        for item in self._all:
            if item in self._areas.GetAllItems():
                self._writeArea(item, asciiFile)
            if item in self._lines.GetAllItems():
                self._writeLine(item, asciiFile)
            if item in self._points.GetAllItems():
                self._writePoint(item, asciiFile)

        asciiFile.close()


        tempVector = 'tmp_rdigit_vector_' + str(os.getpid())
        tempVector2 = 'tmp_rdigit_vector2_' + str(os.getpid())
        tempRaster = 'tmp_rdigit_raster_' + str(os.getpid())
        tempRaster2 = 'tmp_rdigit_raster2_' + str(os.getpid())

        try:
            gcore.run_command('v.in.ascii', input=asciiFile.name, output=tempVector,
                              format='standard', flags='n', quiet=True)
        except CalledModuleError:
            GError(parent=self._mapWindow, message=_("Failed to create a temporary vector map"))
            os.unlink(asciiFile.name)
            return
        gcore.run_command('v.db.addtable', map=tempVector, quiet=True,
                          columns='value double precision, width double precision')
        sql = ''
        for key in self._catToCellValue:
            sql += ("UPDATE {tb} SET value={val},width={w}"
                    " WHERE cat={cat};\n".format(tb=tempVector, cat=key,
                                                 val=self._catToCellValue[key],
                                                 w=self._catToWidthValue[key]))
        gcore.write_command('db.execute', stdin=sql, input='-', quiet=True)
        gcore.run_command('v.buffer', flags='t', input=tempVector, layer=1,
                          output=tempVector2, bufcolumn='width', quiet=True)
        gcore.run_command('v.to.rast', input=tempVector2, output=tempRaster,
                          use='attr', attrcolumn='value', quiet=True)

        gcore.run_command('g.copy', rast=[self._editedRaster, tempRaster2])
        exp = '{edited} = if(! isnull({drawn}), {drawn}, {copied})'.format(
            edited=self._editedRaster.split('@')[0],
            drawn=tempRaster, copied=tempRaster2)

        grast.mapcalc(exp=exp, quiet=True, overwrite=True)

        os.unlink(asciiFile.name)

    def _writeArea(self, item, asciiFile):
        coords = item.GetCoords()
        cat = item.GetPropertyVal('cat')
        cellValue = item.GetPropertyVal('cellValue')
        widthValue = item.GetPropertyVal('widthValue')
        self._catToCellValue[cat] = cellValue
        # v.buffer won't copy features with 0 buffer distance
        # so we set small value (won't work for latlon?)
        if widthValue == 0:
            widthValue = 1e-6
        self._catToWidthValue[cat] = widthValue
        record = 'B {length}\n'.format(length=len(coords) + 1)
        for coord in coords + [coords[0]]:
            record += ' '.join([str(c) for c in coord])
            record += '\n'
        record += 'C 1 1\n'
        x, y = self._getCentroid(coords)
        record += '{x} {y}\n'.format(x=x, y=y)
        record += '1 {cat}\n'.format(cat=cat)

        asciiFile.write(record)

    def _writeLine(self, item, asciiFile):
        self._writeLinePoint(item, vtype='L', asciiFile=asciiFile)

    def _writePoint(self, item, asciiFile):
        self._writeLinePoint(item, vtype='P', asciiFile=asciiFile)

    def _writeLinePoint(self, item, vtype, asciiFile):
        coords = item.GetCoords()
        if vtype == 'P':
            coords = [coords]
        cat = item.GetPropertyVal('cat')
        cellValue = item.GetPropertyVal('cellValue')
        widthValue = item.GetPropertyVal('widthValue')
        self._catToCellValue[cat] = cellValue
        # v.buffer won't copy features with 0 buffer distance
        # so we set small value (won't work for latlon?)
        if widthValue == 0:
            widthValue = 1e-6
        self._catToWidthValue[cat] = widthValue
        record = '{vtype} {length} 1\n'.format(vtype=vtype, length=len(coords))
        for coord in coords:
            record += ' '.join([str(c) for c in coord])
            record += '\n'
        record += '1 {cat}\n'.format(cat=cat)

        asciiFile.write(record)

    def _getCentroid(self, coords):
        x = y = 0
        for xc, yc in coords:
            x += xc
            y += yc
        x /= len(coords)
        y /= len(coords)
        return x, y

# -*- coding: utf-8 -*-
import os
import tempfile
import wx
import uuid

from grass.script import core as gcore
from grass.script import raster as grast
from grass.exceptions import CalledModuleError, ScriptError
from grass.pydispatch.signal import Signal

from core.gcmd import GError, GMessage
from core.settings import UserSettings
from rdigit.dialogs import NewRasterDialog


class RDigitController:
    def __init__(self, giface, mapWindow):
        self._giface = giface
        self._mapWindow = mapWindow

        self._editedRaster = None
        self._backgroundRaster = None
        self._backupRasterName = None
        self._areas = None
        self._lines = None
        self._points = None
        self._all = []
        self._drawing = False
        self._graphicsType = 'area'
        self._currentCellValue = None
        self._currentWidthValue = None
        self._catCount = 1

        self._oldMouseUse = None
        self._oldCursor = None

        self.newRasterCreated = Signal('RDigitController:newRasterCreated')
        self.newFeatureCreated = Signal('RDigitController:newFeatureCreated')
        self.uploadMapCategories = Signal('RDigitController:uploadMapCategories')

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
        self._lines.Draw(pdc=self._mapWindow.pdcTmp)
        self._areas.Draw(pdc=self._mapWindow.pdcTmp)
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

        self.Cleanup()

    def SelectOldMap(self, name):
        try:
            self._backupRaster(name)
        except ScriptError:
            GError(parent=self._mapWindow, message=_("Failed to create backup copy of edited raster map."))
            return False
        self._editedRaster = name
        return True

    def SelectNewMap(self):
        dlg = NewRasterDialog(parent=self._mapWindow)
        if dlg.ShowModal() == wx.ID_OK:
            try:
                self._createNewMap(mapName=dlg.GetMapName(),
                                   backgroundMap=dlg.GetBackgroundMapName(),
                                   mapType=dlg.GetMapType())
            except ScriptError:
                GError(parent=self._mapWindow, message=_("Failed to create new raster map."))
                return False
            finally:
                dlg.Destroy()
            return True
        else:
            dlg.Destroy()
            return False

    def _createNewMap(self, mapName, backgroundMap, mapType):
        name = mapName.split('@')[0]
        background = backgroundMap.split('@')[0]
        types = {'CELL': 'int', 'FCELL': 'float', 'DCELL': 'double'}
        if background:
            back = background
        else:
            back = 'null()'
        try:
            grast.mapcalc(exp="{name} = {mtype}({back})".format(name=name, mtype=types[mapType],
                                                                back=back),
                          overwrite=True, quiet=True)
            if background:
                self._backgroundRaster = backgroundMap
                if mapType == 'CELL':
                    values = gcore.read_command('r.describe', flags='1n',
                                                map=backgroundMap, quiet=True).strip()
                    if values:
                        self.uploadMapCategories.emit(values=values.split('\n'))
        except CalledModuleError:
            raise ScriptError
        self._backupRaster(name)

        name = name + '@' + gcore.gisenv()['MAPSET']
        self._editedRaster = name
        self.newRasterCreated.emit(name=name)

    def _backupRaster(self, name):
        name = name.split('@')[0]
        backup = name + '_backupcopy_' + str(os.getpid())
        try:
            gcore.run_command('g.copy', rast=[name, backup], quiet=True)
        except CalledModuleError:
            raise ScriptError

        self._backupRasterName = backup

    def _exportRaster(self):
        if not self._editedRaster:
            return

        tempRaster = 'tmp_rdigit_rast_' + str(os.getpid())
        text = []
        rastersToPatch = []
        for item in self._all:
            if item.GetPropertyVal('widthValue'):
                if text:
                    out = self._rasterize(text, item.GetPropertyVal('widthValue'), tempRaster)
                    rastersToPatch.append(out)
                    text = []
                self._writeItem(item, text)
                out = self._rasterize(text, item.GetPropertyVal('widthValue'),
                                      tempRaster)
                rastersToPatch.append(out)
                text = []
            else:
                self._writeItem(item, text)
        if text:
            out = self._rasterize(text, item.GetPropertyVal('widthValue'),
                                  tempRaster)
            rastersToPatch.append(out)

#        gcore.run_command('g.copy', rast=[self._editedRaster, tempRaster], overwrite=True, quiet=True)
        gcore.run_command('r.patch', input=sorted(rastersToPatch, reverse=True) + [self._backupRasterName],
                          output=self._editedRaster, overwrite=True, quiet=True)
        gcore.run_command('g.remove', type='rast', flags='f', name=rastersToPatch + [tempRaster],
                          quiet=True)
        try:
            if not self._backgroundRaster:
                table = UserSettings.Get(group='rasterLayer', key='colorTable', subkey='selection')
                gcore.run_command('r.colors', color=table, map=self._editedRaster, quiet=True)
            else:
                gcore.run_command('r.colors', map=self._editedRaster,
                                  raster=self._backgroundRaster, quiet=True)
        except CalledModuleError:
            GError(parent=self._mapWindow,
                   message=_("Failed to set default color table for edited raster map"))

    def _writeFeature(self, item, vtype, text):
        coords = item.GetCoords()
        if vtype == 'P':
            coords = [coords]
        cellValue = item.GetPropertyVal('cellValue')
        record = '{vtype}\n'.format(vtype=vtype)
        for coord in coords:
            record += ' '.join([str(c) for c in coord])
            record += '\n'
        record += '= {cellValue}\n'.format(cellValue=cellValue)

        text.append(record)

    def _writeItem(self, item, text):
        if item in self._areas.GetAllItems():
            self._writeFeature(item, vtype='A', text=text)
        elif item in self._lines.GetAllItems():
            self._writeFeature(item, vtype='L', text=text)
        elif item in self._points.GetAllItems():
            self._writeFeature(item, vtype='P', text=text)

    def _rasterize(self, text, bufferDist, tempRaster):
        output = 'x' + str(uuid.uuid4())[:8]
        asciiFile = tempfile.NamedTemporaryFile(delete=False)
        asciiFile.write('\n'.join(text))
        asciiFile.close()
        if bufferDist:
            gcore.run_command('r.in.poly', input=asciiFile.name, output=tempRaster,
                              overwrite=True, quiet=True)
            gcore.run_command('r.grow', input=tempRaster, output=output,
                              flags='m', radius=bufferDist, quiet=True)
        else:
            gcore.run_command('r.in.poly', input=asciiFile.name, output=output,
                              quiet=True)
        os.unlink(asciiFile.name)
        return output

    def Cleanup(self):
        try:
            gcore.run_command('g.remove', type='rast', flags='f', name=self._backupRasterName, quiet=True)
        except CalledModuleError:
            return

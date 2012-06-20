import os
import string
from __main__ import vtk, qt, ctk, slicer
from DICOMLib import DICOMPlugin
from DICOMLib import DICOMLoadable

#
# This is the plugin to handle translation of DICOM objects
# that can be represented as multivolume objects
# from DICOM files into MRML nodes.  It follows the DICOM module's
# plugin architecture.
#

class MultiVolumeImporterPluginClass(DICOMPlugin):
  """ MV specific interpretation code
  """

  def __init__(self,epsilon=0.01):
    super(MultiVolumeImporterPluginClass,self).__init__()
    self.loadType = "MultiVolume"

  def examine(self,fileLists):
    """ Returns a list of DICOMLoadable instances
    corresponding to ways of interpreting the 
    fileLists parameter.
    """
    loadables = []
    for files in fileLists:
      loadables += self.examineFiles(files)
    return loadables

  def examineFiles(self,files):

    print("MultiVolumeImportPlugin::examine")

    """ Returns a list of DICOMLoadable instances
    corresponding to ways of interpreting the 
    files parameter.
    """
    loadables = []

    # Look for series with several values in either of the volume-identifying
    #  tags in files

    # first separate individual series, then try to find multivolume in each
    # of the series (code from DICOMScalarVolumePlugin)
    subseriesLists = {}
    subseriesDescriptions = {}

    for file in files:

      slicer.dicomDatabase.loadFileHeader(file)
      v = slicer.dicomDatabase.headerValue("0020,000E") # SeriesInstanceUID
      d = slicer.dicomDatabase.headerValue("0008,103e") # SeriesDescription

      try:
        value = v[v.index('[')+1:v.index(']')]
      except ValueError:
        value = "Unknown"

      try:
        desc = d[d.index('[')+1:d.index(']')]
      except ValueError:
        desc = "Unknown"
 
      if not subseriesLists.has_key(value):
        subseriesLists[value] = []
      subseriesLists[value].append(file)
      subseriesDescriptions[value] = desc

    # now iterate over all subseries file lists and try to parse the
    # multivolumes

    mvNode = None
    for key in subseriesLists.keys():
      if mvNode == None:
        mvNode = slicer.mrmlScene.CreateNodeByClass('vtkMRMLMultiVolumeNode')
        mvNode.SetName('MultiVolume node')
        mvNode.SetScene(slicer.mrmlScene)
      
      filevtkStringArray = vtk.vtkStringArray()
      for item in subseriesLists[key]:
        filevtkStringArray.InsertNextValue(item)

      nFrames = slicer.modules.multivolumeexplorer.logic().InitializeMultivolumeNode(filevtkStringArray, mvNode)

      if nFrames > 1:
        tagName = mvNode.GetAttribute('MultiVolume.FrameIdentifyingDICOMTagName')
        loadable = DICOMLib.DICOMLoadable()
        loadable.files = files
        loadable.name = desc + ' - as a ' + str(nFrames) + ' frames MultiVolume by ' + tagName
        loadable.tooltip = loadable.name
        loadable.selected = True
        loadable.multivolume = mvNode
        loadables.append(loadable)

        mvNode = None
      else:
        print('No multivolumes found!')

    if mvNode != None:
      mvNode.SetReferenceCount(mvNode.GetReferenceCount()-1)

    return loadables

  def load(self,loadable):
    """Load the selection as a MultiVolume, if multivolume attribute is
    present
    """

    mvNode = ''
    try:
      mvNode = loadable.multivolume
    except AttributeError:
      return

    print('MultiVolumeImportPlugin load()')
    # create a clean temporary directory
    tmpDir = slicer.app.settings().value('Modules/TemporaryDirectory')
    if not os.path.exists(tmpDir):
      os.mkdir(tmpDir)
    tmpDir = tmpDir+'/MultiVolumeImportPlugin'
    if not os.path.exists(tmpDir):
      os.mkdir(tmpDir)
    else:
      # clean it up
      print 'tmpDir = '+tmpDir
      fileNames = os.listdir(tmpDir)
      for f in fileNames:
        os.unlink(tmpDir+'/'+f)

    nFrames = int(mvNode.GetAttribute('MultiVolume.NumberOfFrames'))
    files = string.split(mvNode.GetAttribute('MultiVolume.FrameFileList'),' ')
    nFiles = len(files)
    filesPerFrame = nFiles/nFrames
    frames = []

    mvImage = vtk.vtkImageData()
    mvImageArray = None

    scalarVolumePlugin = slicer.modules.dicomPlugins['DICOMScalarVolumePlugin']()

    # read each frame into scalar volume
    volumesLogic = slicer.modules.volumes.logic()
    for frameNumber in range(nFrames):
      
      sNode = slicer.vtkMRMLVolumeArchetypeStorageNode()
      sNode.SetFileName(files[0])
      sNode.ResetFileNameList();

      frameFileList = files[frameNumber*filesPerFrame:(frameNumber+1)*filesPerFrame]
      # sv plugin will sort the filenames by geometric order
      svLoadables = scalarVolumePlugin.examine([frameFileList])

      if len(svLoadables) == 0:
        return
      for f in svLoadables[0].files:
        sNode.AddFileName(f)
      
      sNode.SetSingleFile(0)
      frame = slicer.vtkMRMLScalarVolumeNode()
      sNode.ReadData(frame)

      if frame == None:
        print('Failed to read a multivolume frame!')
        return False

      if frameNumber == 0:
        # initialize DWI node based on the parameters of the first frame
        frameImage = frame.GetImageData()
        frameExtent = frameImage.GetExtent()
        frameSize = frameExtent[1]*frameExtent[3]*frameExtent[5]

        mvImage.SetExtent(frameExtent)
        mvImage.SetNumberOfScalarComponents(nFrames)

        mvImage.AllocateScalars()
        mvImageArray = vtk.util.numpy_support.vtk_to_numpy(mvImage.GetPointData().GetScalars())

        # create and initialize a blank DWI node
        bValues = vtk.vtkDoubleArray()
        bValues.Allocate(nFrames)
        bValues.SetNumberOfComponents(1)
        bValues.SetNumberOfTuples(nFrames)
        gradients = vtk.vtkDoubleArray()
        gradients.Allocate(nFrames*3)
        gradients.SetNumberOfComponents(3)
        gradients.SetNumberOfTuples(nFrames)

        bValuesArray = vtk.util.numpy_support.vtk_to_numpy(bValues)
        gradientsArray = vtk.util.numpy_support.vtk_to_numpy(gradients)
        bValuesArray[:] = 0
        gradientsArray[:] = 1

        mvNode.SetScene(slicer.mrmlScene)

        mat = vtk.vtkMatrix4x4()
        frame.GetRASToIJKMatrix(mat)
        mvNode.SetRASToIJKMatrix(mat)
        frame.GetIJKToRASMatrix(mat)
        mvNode.SetIJKToRASMatrix(mat)

      frameImage = frame.GetImageData()
      frameImageArray = vtk.util.numpy_support.vtk_to_numpy(frameImage.GetPointData().GetScalars())
      mvImageArray.T[frameNumber] = frameImageArray
      self.annihilateScalarNode(frame)

    # create additional nodes that are needed for the DWI to be added to the
    # scene
    mvDisplayNode = slicer.mrmlScene.CreateNodeByClass('vtkMRMLMultiVolumeDisplayNode')
    mvDisplayNode.SetScene(slicer.mrmlScene)
    slicer.mrmlScene.AddNode(mvDisplayNode)
    mvDisplayNode.SetReferenceCount(mvDisplayNode.GetReferenceCount()-1)
    mvDisplayNode.SetDefaultColorMap()

    mvNode.SetAndObserveDisplayNodeID(mvDisplayNode.GetID())
    mvNode.SetAndObserveImageData(mvImage)
    mvNode.SetNumberOfFrames(nFrames)
    #mvNode.SetReferenceCount(mvNode.GetReferenceCount()-1)
    print("Number of frames :"+str(nFrames))

    slicer.mrmlScene.AddNode(mvNode)
    print('MV node added to the scene')

    mvNode.SetReferenceCount(mvNode.GetReferenceCount()-1)

    return True

  # leave no trace of the temporary nodes
  def annihilateScalarNode(self, node):
    return
    dn = node.GetDisplayNode()
    sn = node.GetStorageNode()
    node.SetAndObserveDisplayNodeID(None)
    node.SetAndObserveStorageNodeID(None)
    slicer.mrmlScene.RemoveNode(dn)
    slicer.mrmlScene.RemoveNode(sn)
    slicer.mrmlScene.RemoveNode(node)

'''

* need to decide if import plugin should handle all types of MV
* separate functionality for parsing/detecting and loading?
* C++ code for reading and parsing DICOM header?
* once loadable is determined, need to pass the tag separating individual
* volumes ? !
'''

#
# MultiVolumeImporterPlugin
#

class MultiVolumeImporterPlugin:
  """
  This class is the 'hook' for slicer to detect and recognize the plugin
  as a loadable scripted module
  """
  def __init__(self, parent):
    parent.title = "DICOM MultiVolume Import Plugin"
    parent.categories = ["Developer Tools.DICOM Plugins"]
    parent.contributors = ["Andrey Fedorov, BWH"]
    parent.helpText = """
    Plugin to the DICOM Module to parse and load MultiVolume data from DICOM files.
    No module interface here, only in the DICOM module
    """
    parent.acknowledgementText = """
    This DICOM Plugin was developed by 
    Andrey Fedorov, BWH.
    and was partially funded by NIH grant U01CA151261.
    """

    # don't show this module - it only appears in the DICOM module
    parent.hidden = True

    # Add this extension to the DICOM module's list for discovery when the module
    # is created.  Since this module may be discovered before DICOM itself,
    # create the list if it doesn't already exist.
    try:
      slicer.modules.dicomPlugins
    except AttributeError:
      slicer.modules.dicomPlugins = {}
    slicer.modules.dicomPlugins['MultiVolumeImporterPlugin'] = MultiVolumeImporterPluginClass

#
#

class MultiVolumeImporterPluginWidget:
  def __init__(self, parent = None):
    self.parent = parent
    
  def setup(self):
    # don't display anything for this widget - it will be hidden anyway
    pass

  def enter(self):
    pass
    
  def exit(self):
    pass
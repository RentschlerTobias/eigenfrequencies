 
import os
from dtOOPythonSWIG import *
import shutil

class createStatesAndMeshes:
  def CreateStates(self, state):
    xmlName = os.path.join(state + ".xml")
    dtXmlParser.init("tistos_files/machine.xml", xmlName)
    parser = dtXmlParser.reference()
    parser.parse()
    bC = baseContainer()
    cV = labeledVectorHandlingConstValue()
    aF = labeledVectorHandlingAnalyticFunction()
    aG = labeledVectorHandlingAnalyticGeometry()
    bV = labeledVectorHandlingBoundedVolume()
    dC = labeledVectorHandlingDtCase()
    dP = labeledVectorHandlingDtPlugin()
    parser.createConstValue(cV)
    parser.loadStateToConst(state, cV)
    parser.destroyAndCreate(bC, cV, aF, aG, bV, dC, dP)
    #dP.get('csv_meanplane').apply()
    dP.get('ru_adjustDomain').apply()
    os.remove(xmlName)
    parser.extract(state, cV, xmlName)

  def CreateMeshes(self, state, caseName, cfdMesh = True):
    xmlName = os.path.join(state + ".xml")
    dtXmlParser.init("tistos_files/machine.xml", xmlName)
    parser = dtXmlParser.reference()
    parser.parse()
    bC = baseContainer()
    cV = labeledVectorHandlingConstValue()
    aF = labeledVectorHandlingAnalyticFunction()
    aG = labeledVectorHandlingAnalyticGeometry()
    bV = labeledVectorHandlingBoundedVolume()
    dC = labeledVectorHandlingDtCase()
    dP = labeledVectorHandlingDtPlugin()
    parser.createConstValue(cV)
    parser.loadStateToConst(state, cV)
    parser.destroyAndCreate(bC, cV, aF, aG, bV, dC, dP)
    if cfdMesh:
      # make cfd mesh
      for i in (["_n"]):
        dC.get(caseName + i).runCurrentState()

  def Replicate(self, state):
    xmlName = os.path.join(state + ".xml")
    dtXmlParser.init("machine.xml", xmlName)
    parser = dtXmlParser.reference()
    parser.parse()
    container = dtBundle()
    bC = container.cptr_bC()
    cV = container.cptr_cV() 
    aF = container.cptr_aF()
    aG = container.cptr_aG()
    bV = container.cptr_bV()
    dC = container.cptr_dC()
    dP = container.cptr_dP()
    parser.createConstValue(cV)
    parser.loadStateToConst(state, cV)
    parser.destroyAndCreate(bC, cV, aF, aG, bV, dC, dP)
    return container

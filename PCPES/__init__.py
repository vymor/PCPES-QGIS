from qgis.core import QgsApplication
from .protection_algorithm import CoastalProtectionESAlgorithm

def classFactory(iface):
    return CoastalProtectionESAlgorithmInstance()

class CoastalProtectionESAlgorithmInstance:
    def __init__(self):
        self.provider = None

    def initGui(self):
        self.initProcessing()

    def initProcessing(self):
        from .protection_provider import CoastalProtectionProvider
        self.provider = CoastalProtectionProvider()
        QgsApplication.processingRegistry().addProvider(self.provider)

    def unload(self):
        if self.provider:
            QgsApplication.processingRegistry().removeProvider(self.provider)
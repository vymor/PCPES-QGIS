from qgis.core import QgsProcessingProvider
from .protection_algorithm import CoastalProtectionESAlgorithm

class CoastalProtectionProvider(QgsProcessingProvider):
    def __init__(self):
        QgsProcessingProvider.__init__(self)

    def unload(self):
        pass

    def loadAlgorithms(self):
        self.addAlgorithm(CoastalProtectionESAlgorithm())

    def id(self):
        return 'coastal_es_provider'

    def name(self):
        return 'Coastal Ecosystem Services'

    def icon(self):
        return QgsProcessingProvider.icon(self)
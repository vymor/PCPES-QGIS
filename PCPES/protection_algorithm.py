import math
import time
from qgis.PyQt.QtCore import QCoreApplication, QVariant
from qgis.core import (
    QgsProcessing,
    QgsProcessingAlgorithm,
    QgsProcessingParameterVectorLayer,
    QgsProcessingParameterNumber,
    QgsProcessingParameterFeatureSink,
    QgsProcessingException,
    QgsFields,
    QgsField,
    QgsFeature,
    QgsGeometry,
    QgsLineString,
    QgsPointXY,
    QgsSpatialIndex,
    QgsProject,
    QgsFeatureSink,
    QgsCoordinateTransform
)

class CoastalProtectionESAlgorithm(QgsProcessingAlgorithm):
    # FIXED INTERNAL CONSTANTS
    ANGLE_RANGE = 22.5
    CLIP_DISTANCE = 1.0
    FIXED_ANGLES = [
        11.25, 33.75, 56.25, 78.75, 101.25, 123.75, 146.25, 168.75,
        191.25, 213.75, 236.25, 258.75, 281.25, 303.75, 326.25, 348.75
    ]

    def tr(self, string):
        return QCoreApplication.translate('Processing', string)

    def createInstance(self):
        return CoastalProtectionESAlgorithm()

    def name(self):
        return 'Potential_Coastal_Protection_Ecosystem_Service_of_Seagrasses'

    def displayName(self):
        return self.tr('Potential Coastal Protection Ecosystem Service of Seagrasses')

    def group(self):
        return self.tr('Ecosystem Services')

    def groupId(self):
        return 'ecosystem_services'

    def shortHelpString(self):
        return self.tr(
            "<h3>This tool evaluates the coastal protective capacity of seagrass meadows, providing indicative levels of their coastal protection ecosystem service.</h3>"
            "<b>Inputs:</b>"
            "<ul>"
            "<li><b>Coastline:</b> The target line where the results are generated.</li>"
            "<li><b>Land:</b> A landmass polygon layer of the wider area of interest (used for fetch ray clipping).</li>"
            "<li><b>REI:</b> A point layer containing the products of the mean wind velocity and corresponding frequency for each of the 16 circle sectors, considering the 10% highest wind velocity records of the used dataset. They will be combined with the fetch lines for calculating the Relative Exposure Index at the investigated coastal segments.</li>"
            "<li><b>Seagrass layers:</b> Polygons representing the spatial extent of the seagrass meadows under consideration. 'Seagrasses' refer to the total extent and 'Seagrasses Shallow' refer to the extent of those distributed in water depths 0-5m.</li>"
            "</ul>"
            "<p><i>* Note: Coastline input layer must be projected in a metric CRS.</i></p>"
            "<br>"
            "<b>Calculation Logic:</b>"
            "<p>The tool segmentizes the coastline under investigation and casts sets of seaward lines, which are used to approximate the three considered factors that favor the coastal protection functionality of seagrasses, i.e. the spatial extent of the seagrass meadows (both in total and for meadows distributed in water depths 0-5m) and their exposure to high wave activity (based on the REI concept). After a sectoral analysis, averaging and normalizing the values, three scores are resulted, corresponding to each criterion. The weighted mean of these three scores is the final score of each segment.</p>"
            "<b>Weights:</b>"
            "<p>The default weights of importance of the considered criteria are based on literature evidence for the purpose of this research. They can be modified in case the user prefers to use available local knowledge or expert judgment values, or for calibrating the tool per case.</p>"
        )

    def initAlgorithm(self, config=None):
        # INPUTS
        self.addParameter(QgsProcessingParameterVectorLayer('coastline', self.tr('Coastline'), [QgsProcessing.TypeVectorLine]))
        self.addParameter(QgsProcessingParameterVectorLayer('land', self.tr('Land'), [QgsProcessing.TypeVectorPolygon]))
        self.addParameter(QgsProcessingParameterVectorLayer('REI', self.tr('REI'), [QgsProcessing.TypeVectorPoint]))
        self.addParameter(QgsProcessingParameterVectorLayer('seagrasses', self.tr('Seagrasses'), [QgsProcessing.TypeVectorPolygon]))
        self.addParameter(QgsProcessingParameterVectorLayer('seagrasses_swallow', self.tr('Seagrasses Shallow'), [QgsProcessing.TypeVectorPolygon]))
        
        # USER CONFIG
        self.addParameter(QgsProcessingParameterNumber('segment_length', self.tr('Segment Length (m)'), defaultValue=250))
        self.addParameter(QgsProcessingParameterNumber('transects_per_segment', self.tr('Transects per Segment'), defaultValue=50))
        self.addParameter(QgsProcessingParameterNumber('max_fetch_dist', self.tr('Maximum Fetch Distance (m)'), defaultValue=200000))

        # USER WEIGHTS
        self.addParameter(QgsProcessingParameterNumber('weight_C1', self.tr('Weight for Criterion 1 (Seagrasses Shallow)'), defaultValue=0.58, type=QgsProcessingParameterNumber.Double))
        self.addParameter(QgsProcessingParameterNumber('weight_C2', self.tr('Weight for Criterion 2 (Seagrasses)'), defaultValue=0.31, type=QgsProcessingParameterNumber.Double))
        self.addParameter(QgsProcessingParameterNumber('weight_C3', self.tr('Weight for Criterion 3 (REI)'), defaultValue=0.11, type=QgsProcessingParameterNumber.Double))

        self.addParameter(QgsProcessingParameterFeatureSink('OUTPUT', self.tr('Coastal Protection Segments')))

    def processAlgorithm(self, parameters, context, feedback):
        # Resolve Layers
        coast_layer = self.parameterAsVectorLayer(parameters, 'coastline', context)
        land_layer = self.parameterAsVectorLayer(parameters, 'land', context)
        met_layer = self.parameterAsVectorLayer(parameters, 'REI', context)
        sg1_layer = self.parameterAsVectorLayer(parameters, 'seagrasses', context)
        sg2_layer = self.parameterAsVectorLayer(parameters, 'seagrasses_swallow', context)

        seg_len = self.parameterAsDouble(parameters, 'segment_length', context)
        transects = self.parameterAsInt(parameters, 'transects_per_segment', context)
        max_fetch = self.parameterAsDouble(parameters, 'max_fetch_dist', context)
        W1, W2, W3 = self.parameterAsDouble(parameters, 'weight_C1', context), self.parameterAsDouble(parameters, 'weight_C2', context), self.parameterAsDouble(parameters, 'weight_C3', context)

        source_crs = coast_layer.crs()

        # CRITICAL FAILSAFE: The Coastline MUST be in meters (Projected) to cut 250m pieces accurately
        if source_crs.isGeographic():
            raise QgsProcessingException(
                "❌ COASTLINE PROJECTION ERROR: Your Coastline layer is in a geographic coordinate system (degrees).\n"
                "The algorithm requires a metric layout to cut accurate segments. Please export your "
                "coastline layer to a projected coordinate framework before running."
            )

        # 1. FIELD PREPARATION (Modern API Syntax - Zero Warnings)
        fields = QgsFields()
        fields.append(QgsField("Seg_ID", QVariant.Type(QVariant.Int)))
        for i in range(1, 17):
            fields.append(QgsField(f"Sector {i}", QVariant.Type(QVariant.Double)))
            fields.append(QgsField(f"fetch{i}", QVariant.Type(QVariant.Double)))
            fields.append(QgsField(f"SG_Len_{i}", QVariant.Type(QVariant.Double)))
            fields.append(QgsField(f"SG2_Len_{i}", QVariant.Type(QVariant.Double)))
        
        fields.append(QgsField("C3_AVG", QVariant.Type(QVariant.Double)))
        fields.append(QgsField("C2_AVG", QVariant.Type(QVariant.Double)))
        fields.append(QgsField("C1_AVG", QVariant.Type(QVariant.Double)))
        fields.append(QgsField("C3", QVariant.Type(QVariant.Double)))
        fields.append(QgsField("C2", QVariant.Type(QVariant.Double)))
        fields.append(QgsField("C1", QVariant.Type(QVariant.Double)))
        fields.append(QgsField("PROT_SCORE", QVariant.Type(QVariant.Double)))

        (sink, dest_id) = self.parameterAsSink(parameters, 'OUTPUT', context, fields, coast_layer.wkbType(), source_crs)

        # 2. IN-MEMORY CRS RE-PROJECTION ALIGNMENT
        feedback.pushInfo("🔄 Background check: Aligning input spatial dimensions to Coastline CRS...")
        
        # Setup transformation pipelines targeting the Coastline's CRS
        transform_met = QgsCoordinateTransform(met_layer.crs(), source_crs, context.transformContext())
        transform_land = QgsCoordinateTransform(land_layer.crs(), source_crs, context.transformContext())
        transform_sg1 = QgsCoordinateTransform(sg1_layer.crs(), source_crs, context.transformContext())
        transform_sg2 = QgsCoordinateTransform(sg2_layer.crs(), source_crs, context.transformContext())

        # Initialize spatial indices cleanly
        met_idx = QgsSpatialIndex()
        land_idx = QgsSpatialIndex()
        sg1_idx = QgsSpatialIndex()
        sg2_idx = QgsSpatialIndex()

        # Safely extract, re-project, and index all layers to the Coastline's CRS
        met_dict = {}
        for f in met_layer.getFeatures():
            feat = QgsFeature(f)
            if feat.hasGeometry():
                geom = feat.geometry()
                geom.transform(transform_met)
                feat.setGeometry(geom)
                met_idx.addFeature(feat)  # Natively adds to the spatial index
            met_dict[feat.id()] = feat
            
        land_dict = {}
        for f in land_layer.getFeatures():
            feat = QgsFeature(f)
            if feat.hasGeometry():
                geom = feat.geometry()
                geom.transform(transform_land)
                feat.setGeometry(geom)
                land_idx.addFeature(feat)
            land_dict[feat.id()] = feat.geometry()

        sg1_dict = {}
        for f in sg1_layer.getFeatures():
            feat = QgsFeature(f)
            if feat.hasGeometry():
                geom = feat.geometry()
                geom.transform(transform_sg1)
                feat.setGeometry(geom)
                sg1_idx.addFeature(feat)
            sg1_dict[feat.id()] = feat.geometry()

        sg2_dict = {}
        for f in sg2_layer.getFeatures():
            feat = QgsFeature(f)
            if feat.hasGeometry():
                geom = feat.geometry()
                geom.transform(transform_sg2)
                feat.setGeometry(geom)
                sg2_idx.addFeature(feat)
            sg2_dict[feat.id()] = feat.geometry()
        
        met_f_names = [f.name() for f in met_layer.fields()]

        # ==============================================================================
        # === 3. SEGMENTATION & REI TRANSFER ===
        # ==============================================================================
        feedback.setProgressText("Initializing coastline segmentation...")
        features_list = []
        seg_id = 1

        for f in coast_layer.getFeatures():
            geom = f.geometry()
            if geom.isNull(): 
                continue
                
            lines = geom.asMultiPolyline() if geom.isMultipart() else [geom.asPolyline()]
            for nodes in lines:
                if not nodes: 
                    continue
                
                line_string = QgsLineString(nodes)
                l_len = line_string.length()
                curr = 0
                
                while curr < l_len:
                    sub_line_abstract = line_string.curveSubstring(curr, curr + seg_len)
                    
                    feat = QgsFeature(fields)
                    feat.setGeometry(QgsGeometry(sub_line_abstract))
                    
                    # Pre-initialize sector attribute fields to 0.0 to prevent NULL math errors
                    for i in range(1, 17):
                        feat.setAttribute(f"Sector {i}", 0.0)
                    
                    # Calculate segment midpoint (Now perfectly aligned natively)
                    mid_pt = feat.geometry().interpolate(feat.geometry().length() / 2).asPoint()
                    
                    # Search the spatial index (Will always succeed since all maps share the exact same grid now)
                    nids = met_idx.nearestNeighbor(mid_pt, 1)
                    
                    if nids:
                        m_feat = met_dict[nids[0]]
                        for i in range(1, 17):
                            cands = [f"Sector {i}", f"Sector_{i}", f"sector {i}", f"sector_{i}", f"Sector{i}"]
                            found_val = 0.0
                            for c in cands:
                                if c in met_f_names:
                                    found_val = float(m_feat.attribute(c) or 0.0)
                                    break
                            feat.setAttribute(f"Sector {i}", found_val)
                    
                    feat.setAttribute("Seg_ID", seg_id)
                    features_list.append(feat)
                    curr += seg_len
                    seg_id += 1
                    
        feedback.pushInfo(f"Successfully generated {len(features_list)} coastal segments for analysis.")
        
        # 4. RAY CASTING (Calculates fetch, SG_Len, SG2_Len)
        feedback.pushInfo("Step 2: Casting rays for all 16 directions...")
        for sector_idx, base_angle in enumerate(self.FIXED_ANGLES, start=1):
            if feedback.isCanceled(): break
            feedback.setProgress(int((sector_idx/16)*100))
            
            for f in features_list:
                sid = f.attribute("Seg_ID")
                geom = f.geometry()
                nodes = max(geom.asMultiPolyline(), key=len) if geom.isMultipart() else geom.asPolyline()
                s_geom = QgsGeometry.fromPolylineXY(nodes)
                step = s_geom.length() / (transects + 1)
                
                f_acc_num, f_acc_den, s1_acc, s2_acc = 0.0, 0.0, 0.0, 0.0
                
                for j in range(transects):
                    a_rad = math.radians((base_angle + self.ANGLE_RANGE/2) - (j * (self.ANGLE_RANGE/(transects-1))))
                    orig = s_geom.interpolate((j+1)*step).asPoint()
                    targ = QgsPointXY(orig.x() + max_fetch * math.sin(a_rad), orig.y() + max_fetch * math.cos(a_rad))
                    
                    # Fetch
                    s_hit = max_fetch
                    t_ray = QgsGeometry.fromPolylineXY([QgsGeometry.fromPolylineXY([orig, targ]).interpolate(self.CLIP_DISTANCE).asPoint(), targ])
                    for l_id in land_idx.intersects(t_ray.boundingBox()):
                        if t_ray.intersects(land_dict[l_id]):
                            d = QgsGeometry.fromPointXY(orig).distance(t_ray.intersection(land_dict[l_id]))
                            if d < s_hit: s_hit = d
                    
                    c_theta = math.cos(a_rad - math.radians(base_angle))
                    f_acc_num += s_hit * c_theta
                    f_acc_den += c_theta
                    
                    # Seagrass
                    c_ray = QgsGeometry.fromPolylineXY([orig, QgsPointXY(orig.x() + s_hit * math.sin(a_rad), orig.y() + s_hit * math.cos(a_rad))])
                    def get_l(g, idx, d): return sum(g.intersection(d[s]).length() for s in idx.intersects(g.boundingBox()) if g.intersects(d[s]))
                    s1_acc += get_l(c_ray, sg1_idx, sg1_dict)
                    s2_acc += get_l(c_ray, sg2_idx, sg2_dict)

                f.setAttribute(f"fetch{sector_idx}", f_acc_num/f_acc_den if f_acc_den > 0 else 0)
                f.setAttribute(f"SG_Len_{sector_idx}", s1_acc/transects)
                f.setAttribute(f"SG2_Len_{sector_idx}", s2_acc/transects)

        # 5. FINAL CALCULATIONS
        feedback.pushInfo("Step 3: Calculating Scores and Normalization...")
         
        # Calculate sums/avgs for all features first and then Normalize
        r_sum_list = [sum(float(f[f"fetch{i}"] or 0) * float(f[f"Sector {i}"] or 0) for i in range(1, 17)) for f in features_list]
        s1_avg_list = [sum(float(f[f"SG_Len_{i}"] or 0) for i in range(1, 17))/16 for f in features_list]
        s2_avg_list = [sum(float(f[f"SG2_Len_{i}"] or 0) for i in range(1, 17))/16 for f in features_list]
 
        rmin, rmax = min(r_sum_list), max(r_sum_list)
        joint_min = min(min(s1_avg_list), min(s2_avg_list))
        joint_max = max(max(s1_avg_list), max(s2_avg_list))
 
        for i, f in enumerate(features_list):
            rv, s1v, s2v = r_sum_list[i], s1_avg_list[i], s2_avg_list[i]
             
            c3_s = (rmax - rv) / (rmax - rmin) if rmax > rmin else 1.0
            c2_s = (s1v - joint_min) / (joint_max - joint_min) if joint_max > joint_min else 0
            c1_s = (s2v - joint_min) / (joint_max - joint_min) if joint_max > joint_min else 0
            
            # The Final Protection Score (Weighted mean of C1, C2 and C3)
            if c2_s > 0:
                score2 = (c1_s * W1 + c2_s * W2 + c3_s * W3) / (W1 + W2 + W3)
            else:
                score2 = 0.0
                
            f.setAttribute("C3_AVG", rv); f.setAttribute("C2_AVG", s1v); f.setAttribute("C1_AVG", s2v)
            f.setAttribute("C3", round(c3_s, 6)); f.setAttribute("C2", round(c2_s, 6)); f.setAttribute("C1", round(c1_s, 6))
            f.setAttribute("PROT_SCORE", round(score2, 6))
            
            sink.addFeature(f, QgsFeatureSink.FastInsert)
 
        return {'OUTPUT': dest_id}
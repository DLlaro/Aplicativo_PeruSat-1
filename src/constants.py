# constants.py

# Satellite specs
PIXEL_SIZE_PERU_SAT= 0.7  # PeruSat-1 native resolution in meters
DEFAULT_SCALED_FACTOR = 50

# UI defaults
DEFAULT_WINDOW_WIDTH = 1200
DEFAULT_WINDOW_HEIGHT = 800
LOGO_SIZE = 300

# ROI visualization
ROI_EDGE_COLOR = "red"
ROI_FACE_COLOR = [1, 0, 0, 0.2]
ROI_EDGE_WIDTH = 2

# Timeouts (milliseconds)
TIMEOUT_SHORT = 2000
TIMEOUT_MEDIUM = 3000
TIMEOUT_LONG = 5000

#Image
MAX_LIMIT_RENDER = 10000
MAX_LIMIT_RENDER_UNLOCK = 20000 #Could check GPU & RAM of the pc to assign a more accurate value

#Analize
MIN_AREA_KM2 = 10

import os
import sys

# los módulos del proyecto se importan desde la raíz (config, core, engine...)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

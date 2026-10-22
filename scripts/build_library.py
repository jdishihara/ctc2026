import json, sys
from pathlib import Path
sys.path.insert(0, '.')
from ctc.analog import build_library
root = Path('data'); man = json.load(open(root / 'history/manifest.json'))
build_library(root, man['seasons'][:450])
print('library built from seasons 1-450')

# SnapIMS 0.6.0 Demo and Pilot Data

Create a deterministic demo camera folder from Python:

```bash
python - <<'PY'
from pathlib import Path
from snapims.demo import create_demo_batch
print(create_demo_batch(Path.home() / "SnapIMS-demo-camera", item_count=20, photos_per_item=2))
PY
```

Launch SnapIMS, open Import, choose the generated folder, Preview, and Preserve and Import Batch.

For a more difficult recognition/import test, use the separately supplied `SnapIMS_Synthetic_Hard_Batch.zip`. Its `import_photos/` directory is the flat chronological camera stream.

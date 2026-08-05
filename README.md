# SnapIMS v0.13.2

SnapIMS is a local, photo-first inventory workstation for Canada VHS. v0.13.2 is a patch release that stabilizes the folder-based Import workflow, corrects Batch Editor consistency problems, prevents mixed-version launches, and bounds large-batch rendering.

## Daily workflow

1. Create one immediate child folder inside `~/SnapIMS-data/batches`.
2. Name the folder with the desired default batch display name.
3. Place product photographs in capture order.
4. Photograph `NEXT ITEM` (`CVHS1:ITEM:NEXT`) between tapes.
5. Open Import, select the folder, and optionally enter any free-text location.
6. Preview, verify grouping, and Commit.
7. Continue through Recognition, Review, Batch Editor, and Publish.

Legacy START, END, LOCATION, RARE, REVIEW, and CONTINUE QR photographs are ignored as non-blocking legacy commands. They do not control grouping.

## Install

```bash
unzip SnapIMS-v0.13.2-full-source.zip
cd SnapIMS-v0.13.2
chmod +x install_v0132.sh
./install_v0132.sh
export PATH="$HOME/.local/bin:$PATH"
snapims version
snapims up
```

The installer pins `~/.local/bin/snapims` and the user service to the extracted v0.13.2 release. `snapims status` prints the resolved project path, venv executable, data directory, PID, application version, and inventory schema.

## Core commands

```bash
snapims up
snapims down
snapims restart
snapims status
snapims doctor
snapims logs
```

## Data safety

Application code and operator data are separate. The default data root is `~/SnapIMS-data`. Original source photographs are never renamed, deleted, recompressed, or modified. Display-name edits do not rename source folders or change immutable Batch/Item IDs.

## Verification

See `TEST_RESULTS.md`, `BROWSER_VERIFICATION.md`, `PERFORMANCE_REPORT.md`, `ISSUE_TRACEABILITY_V0132.md`, and `PRODUCTION_READINESS.md`.

# SnapIMS v0.15.0 Installation Guide

## Clean install

```bash
unzip SnapIMS-v0.15.0-full-source.zip
cd SnapIMS-v0.15.0
chmod +x install_v0150.sh
./install_v0150.sh
export PATH="$HOME/.local/bin:$PATH"
snapims version
snapims doctor
snapims up
```

Expected version: `0.15.0`. Expected inventory schema: `16 / 16`.

## Upgrade from v0.14.0

```bash
snapims down
cp -a ~/SnapIMS-data ~/SnapIMS-data-backup-before-v0150-$(date +%Y%m%d-%H%M%S)
unzip SnapIMS-v0.15.0-full-source.zip
cd SnapIMS-v0.15.0
SNAPIMS_DATA_DIR="$HOME/SnapIMS-data" ./install_v0150.sh
export PATH="$HOME/.local/bin:$PATH"
snapims status
snapims up
```

The installer creates a pre-schema-16 database backup before forward migration and rewrites the launcher/user service to the extracted release. Existing inventory and Shopify linkage IDs are preserved.

After upgrade, open Settings and select a Shopify publication before attempting live publication.

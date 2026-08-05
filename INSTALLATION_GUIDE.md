# SnapIMS v0.13.2 Installation Guide

## Clean install

```bash
unzip SnapIMS-v0.13.2-full-source.zip
cd SnapIMS-v0.13.2
chmod +x install_v0132.sh
./install_v0132.sh
export PATH="$HOME/.local/bin:$PATH"
snapims version
snapims doctor
snapims up
```

## Upgrade

```bash
snapims down
cp -a ~/SnapIMS-data ~/SnapIMS-data-backup-before-v0132-$(date +%Y%m%d-%H%M%S)
unzip SnapIMS-v0.13.2-full-source.zip
cd SnapIMS-v0.13.2
SNAPIMS_DATA_DIR="$HOME/SnapIMS-data" ./install_v0132.sh
export PATH="$HOME/.local/bin:$PATH"
snapims status
snapims up
```

The installer creates schema-15 backups automatically and rewrites the current user launcher/service to this extracted release.

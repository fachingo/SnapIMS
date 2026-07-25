# GitHub Publication Status

Target repository: `fachingo/SnapIMS`  
Target branch: `fix/v0.6.1-mega-stabilization`

The local release branch is complete and clean. A direct push was attempted from the build environment, but its DNS resolver could not resolve `github.com`:

```text
fatal: unable to access 'https://github.com/fachingo/SnapIMS.git/': Could not resolve host: github.com
```

No remote changes were made. No force-push was attempted.

## Publish from MacMint

From the extracted complete repository:

```bash
cd ~/Projects/SnapIMS-v0.6.1
git status
git branch -vv
git remote -v
git push -u origin fix/v0.6.1-mega-stabilization
```

Or import the bundle into an existing clone:

```bash
cd ~/Projects/SnapIMS
git fetch ~/Downloads/SnapIMS-v0.6.1.bundle \
  fix/v0.6.1-mega-stabilization:fix/v0.6.1-mega-stabilization
git switch fix/v0.6.1-mega-stabilization
git push -u origin fix/v0.6.1-mega-stabilization
```

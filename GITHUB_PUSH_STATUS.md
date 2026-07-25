# GitHub Publication Status

Target repository: `fachingo/SnapIMS`  
Target branch: `feature/v0.7.0-keyboard-catalog`

The release is packaged as a complete repository and portable Git bundle. No force-push or automatic merge is performed by the release package.

Publish from MacMint:

```bash
cd ~/Projects/SnapIMS-v0.7.0
git status
git log -1 --oneline
git push -u origin feature/v0.7.0-keyboard-catalog
git push origin v0.7.0
```

Open a pull request into the owner-approved base branch only after CI and the real-operator review of the package.

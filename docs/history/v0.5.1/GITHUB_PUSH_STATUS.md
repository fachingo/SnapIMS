# GitHub Publication Status

Target repository: `fachingo/SnapIMS`  
Target branch: `fix/v0.5.1-verification-hardening`

The connected GitHub App returned `403 Resource not accessible by integration` when branch creation was attempted. No remote branch or `main` content was changed.

## Safe publication from the bundle

```bash
git clone https://github.com/fachingo/SnapIMS.git SnapIMS
cd SnapIMS
git fetch /path/to/SnapIMS-v0.5.1.bundle fix/v0.5.1-verification-hardening:fix/v0.5.1-verification-hardening
git switch fix/v0.5.1-verification-hardening
git push -u origin fix/v0.5.1-verification-hardening
```

Do not merge until CI passes and the branch is reviewed.

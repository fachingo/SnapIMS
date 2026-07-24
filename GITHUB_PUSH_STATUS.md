# GitHub Push Status

The reconstruction package is complete locally, but no GitHub branch was modified.

An attempt to create `reconstruction/snapims-v0.5.0` through the connected GitHub integration returned:

```text
403 Resource not accessible by integration
```

The repository connector could read `fachingo/SnapIMS`, but its write authorization was insufficient for creating the branch. No force push, reset, merge, deletion, or update to `main` was attempted.

## Safe manual publication

From a machine authenticated to GitHub:

```bash
git clone https://github.com/fachingo/SnapIMS.git
cd SnapIMS
git switch -c reconstruction/snapims-v0.5.0

# Extract SnapIMS-v0.5.0.zip elsewhere, then copy its contents into this clone.
# rsync is preferred because it preserves hidden repository files while excluding .git.
rsync -a --delete --exclude='.git' /path/to/SnapIMS-v0.5.0/ ./

git status
git add -A
git commit -m "Reconstruct SnapIMS v0.5.0"
git push -u origin reconstruction/snapims-v0.5.0
```

Do not merge into `main` until GitHub Actions, browser verification on the deployed branch, and review of the generated documentation pass.

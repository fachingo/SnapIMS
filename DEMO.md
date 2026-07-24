# SnapIMS 0.5.1 Demonstration

## Generate a QR-delimited camera roll

```bash
snapims demo demo-data/camera-roll
```

## Start the browser application

```bash
snapims --data-dir demo-data/workspace serve
```

Then use only the browser:

1. Import -> Advanced -> choose `demo-data/camera-roll`.
2. Preview and confirm the non-durable identity and grouping counts.
3. Preserve and import.
4. Continue to Review.
5. Select Mock and Identify items.
6. Confirm title; optionally adjust Price or Discount; select **Approve & Next**.
7. Use Later for a postponed tape or Edit for an exception.
8. Open Publish, simulate drafts, and download the CSV.

Mock is deterministic test data. It does not prove live AI quality.

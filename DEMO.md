# SnapIMS demonstration

Generate a QR-command fixture with 20 VHS records:

```bash
snapims demo demo-data/camera-roll --items 20
snapims serve
```

In the browser:

1. Open **Import**.
2. Under **Advanced**, choose `demo-data/camera-roll` and save it as the incoming folder.
3. Preview. Confirm 20 items, 40 product photographs, and deterministic command counts.
4. Import and continue to Review.
5. Select Mock and identify the batch.
6. Process the fast path with **✓ Approve & Next**.
7. Open Publish, simulate drafts, and download the CSV.

The fixture uses `.qr.txt` sidecars for deterministic automated testing. Real camera photographs continue to use visible QR decoding.

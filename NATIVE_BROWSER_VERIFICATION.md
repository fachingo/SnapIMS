# SnapIMS 0.5.1 Native Browser Verification

## Transport proof

- Application: separate uvicorn process.
- Browser: Chromium driven by Playwright.
- Navigation: real local-loopback HTTP URL.
- Viewport: 1440 x 1000.
- Prohibited shortcuts absent: no TestClient operator transport, no `page.set_content()`, no form replay, and no direct database/service call to complete operator steps.
- Browser-tested code commit: `411b51d9f72c8da1fd7f71eb5a42ae53fdfba026`.

## Browser-observed operator actions

Fresh Home; first-run folder setup; Preview; preserve/import; Continue to Review; start and complete recognition; 20-item fast approval; Price and Discount quick edits; Later and return; Done correction; invalid edit and Cancel; full process restart; Publish simulation; visible CSV download; missing-folder recovery; failed recognition Retry; real interruption and Continue; Settings; Diagnostics.

## Metrics

- 24 clicks / 20 tapes = 1.20 clicks per tape.
- 17/20 true one-click approvals.
- Average application approval-to-next render time: 0.091 seconds.
- Real operator time per tape was not measured.

## Post-audit reconciliation

- Main batch items: 20.
- Browser-downloaded CSV rows: 20.
- Interrupted batch items/results: 40/40.
- Duplicate recognition-attempt items: 0.
- SQLite integrity: ok.
- Foreign-key violations: 0.

Machine-readable evidence: `operator-audit-assets/v0.5.1-browser/native-browser-results.json` and `browser-metrics.json`.

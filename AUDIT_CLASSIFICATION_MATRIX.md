# SnapIMS 0.7.0 Audit Classification Matrix

Branch: `feature/v0.7.0-keyboard-catalog`

| Finding | Disposition | Evidence |
|---|---|---|
| v0.6.1 legacy recognition FK mismatch | Fixed | Schema 8 realistic migration test; browser restart |
| Tkinter missing creates Import dead end | Fixed | fallback route test and final Import UI |
| Ctrl+Shift+P inconsistent | Fixed | capture-phase KeyP plus Ctrl/Cmd+K fallback; browser palette test |
| Empty Title requires extra Enter/editor | Fixed | inline Title one-request test and browser step |
| Batch Editor arrows/selection absent | Fixed | JS keyboard contract and native browser workflow |
| Quick actions need shortcuts/order/help | Fixed | Ctrl/Cmd+1–9, Alt reorder, persistent order, popup descriptions |
| Same-version CSV says Item ID missing | Fixed | exact export round trip and spreadsheet-shaped fixtures |
| Local commercial movie facts unavailable | Implemented as new capability | separate catalog, local-first search, bounded Wikipedia, provenance, jobs and diagnostics |
| Manual catalog request identity collision | Fixed during audit | deterministic negative catalog-only IDs and no false inventory recognition FK |
| 5,000-row editor/10,000-photo import | Deferred | requires Rank-5 architecture and measured target hardware gate |
| Live AI/live Shopify/real Pixel pilot | Blocked external acceptance | mandatory before 1.0.0 |
| Multi-user remote operation | Deferred | application sessions/roles/CSRF/concurrency required |

# SnapIMS v0.13.2 Import Fixture Matrix

| # | Fixture | Expected result |
|---:|---|---|
| 1 | One Item, no NEXT | one valid Item |
| 2 | Two Items, one NEXT | two Items |
| 3 | Twenty Items | 20 Items, 19 NEXT |
| 4-6 | Leading, trailing, consecutive NEXT | valid grouping plus warning |
| 7 | Empty folder | needs attention; no products |
| 8 | NEXT-only folder | needs attention; no products |
| 9 | Corrupt JPEG | readable photos continue; error shown |
| 10 | HEIC/HEIF | decoded when optional runtime exists |
| 11 | Unsupported files | ignored |
| 12 | Consumer QR | product photograph |
| 13-14 | Legacy and malformed LOCATION | ignored, one concise warning |
| 15-17 | Blank, None, arbitrary location | unassigned or accepted free text |
| 18-19 | Spaces and Unicode folder names | preserved and displayed |
| 20 | Reused folder | prior import/resume state shown |
| 21 | File changed after Preview | only changed file rescanned; reconfirm |
| 22-24 | Process/browser interruption | durable recovery |
| 25 | Split and merge corrections | persisted interpretation |
| 26 | One changed cache entry | one miss; unrelated hits retained |
| 27 | 100 Items / 202 photos | bounded memory and warm cache |
| 28 | Multiple child folders | independent batches |
| 29 | Existing v0.12.3 database | forward migration and preservation |
| 30 | Clean install | schema 14 and empty Batch Home |

The deterministic test generator creates real decodable QR photographs rather than parser-only mocks.

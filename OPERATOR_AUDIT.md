# SnapIMS 0.6.1 Operator Audit

The patch preserves the routine rhythm:

1. Look at the photo.
2. Confirm the displayed title or open manual edit when required.
3. Optionally change Price or Discount.
4. Press Enter or choose Approve & Next.
5. The next unfinished tape opens immediately.

High-confidence fixes:

- Price receives focus and Enter advances one tape.
- Suggestions are labelled as suggestions and are not shown as saved values.
- Missing AI credentials lead to a clear manual path, not a dead end.
- Bulk Price is one dialog and one operation.
- CSV upload shows a difference preview before replacing working values.
- Every major terminal state points to the next action.

Deferred operator concerns are warehouse-scale row virtualization and a deeper per-photo import sequence viewer.

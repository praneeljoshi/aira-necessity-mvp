## Policies
- [A] Prune an alternative route only on a fact the order fixes (the product or HCPCS code, the device, an age band,
  the side, the procedure). Keep clinical alternatives the diagnosis does not rule out: the chart will decide them.
- [C] Where the grouping of "and" / "or" is ambiguous, take the stricter reading and write the other reading in `notes`.
- [D] Attach a condition from another section only when the text links it to this indication or procedure (a
  cross-reference, "the criteria above", a defined term it uses, a note or reimbursement rule naming this procedure).
- [E] If a literal condition would make this route impossible (it contradicts what the route is for), leave it out of
  this route and say so in `notes`.

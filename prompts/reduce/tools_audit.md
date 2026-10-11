# Check the logic: find what it lets through

Someone built, with these tools, the logic for the order below. Your job now is to find what it lets through.

Describe patients (or planned procedures) who satisfy the logic as written but whom the guideline's text would deny:
a condition left out, an exclusion or limitation printed elsewhere in the document, a qualifier dropped ("sole", "in
adults", "FDA-approved", "for the treatment of …"), an OR that should be an AND, a waiver applied too broadly, an
example list read as closed. Use `find` and `read` to look. Then close each gap: `add_condition` for what is missing
and `set_logic` again for the indication you tighten.

You may only tighten. `set_logic` refuses logic that drops an existing condition, and you cannot add a new
indication, change or remove a condition, or redefine a block. If you find nothing, call `submit` with no change.

Finish with `submit`: `indication_quotes` as already given (or [] when you add none), and in `notes` one line per
patient you found, starting each with "- " (or "none found").

## The current tree

{{tree}}

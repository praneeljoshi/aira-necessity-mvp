Now check yourself. Describe patients (or planned procedures) who satisfy the expression in `tree.json` but whom the
guideline's text would deny: a condition left out, an exclusion or limitation printed elsewhere in the document, a
qualifier dropped ("sole", "in adults", "FDA-approved", "for the treatment of …"), an `any` that should be an `all`, a
waiver applied too broadly, an example list read as closed.

For each one, edit `tree.py` to close it: add the missing condition (quoted) or tighten the logic. You may only add or
tighten: keep every existing condition in the expression. Re-run until it prints OK.

Final message: one line per patient you found (or "none found"), then "DONE".

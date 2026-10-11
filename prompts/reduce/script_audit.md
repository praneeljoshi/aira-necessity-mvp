# Check the script: find what it lets through

Someone wrote the tree script below for this order, and it passes the checks. Your job now is to find what it lets
through.

Describe patients (or planned procedures) who satisfy the logic as written but whom the guideline's text would deny:
a condition left out, an exclusion or limitation printed elsewhere in the document, a qualifier dropped ("sole", "in
adults", "FDA-approved", "for the treatment of …"), an OR that should be an AND, a waiver applied too broadly, an
example list read as closed. Use `find` and `read` to look. Then close each gap by editing the script: add conditions
and tighten the logic.

You may only tighten: keep every condition and every indication, and keep every condition each indication's logic
already uses (the host refuses a script that drops one). Do not add a new indication.

For each patient you found, add one line to the script: `notes("- <the patient, and what you added>")`. If you find
nothing, add `notes("none found")`. Then `submit` the whole script.

## The script

```python
{{script}}
```

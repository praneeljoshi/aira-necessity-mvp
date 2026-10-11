{{brief}}

---

## No sandbox in this run: return the tree as JSON

There is no `helpers.py` to run here. Return one JSON object; the host runs the same checks (every quote found in the
guideline, ids unique, every leaf a condition or block, every condition used, the expression parses) and sends back any
problems.

```
{"indication": ["the guideline's sentence(s) that grant the indication(s) used, quoted exactly"],
 "not_covered": null,
 "conditions": [{"id": "reflux", "quote": "There is demonstrated saphenous reflux", "question": "…", "threshold": null, "answerable": true},
                {"id": "ahi_15", "quote": "…", "question": "…", "threshold": {"op": ">=", "value": 15, "unit": "events/hour"}, "answerable": true}],
 "blocks": [{"name": "osa_adult", "expr": {"all": ["ahi_15", "adult"]}}],
 "expression": {"all": ["reflux", "osa_adult", {"not": "dvt"}]},
 "notes": "judgment calls and alternative readings"}
```

## The order

{{order_json}}

## The indication

{{indication}}

## guideline.txt

{{guideline}}

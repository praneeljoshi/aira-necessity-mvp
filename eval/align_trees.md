You align the leaves of two requirement trees built from the same section of a payer coverage guideline. Tree T is
an answer key; tree G was built by a system under test. You do not judge which tree is right. You only say, for every
G leaf, which T leaf or leaves it asks about, so that code can compare the trees' logic exactly.

For each G leaf return one link:
- `same`: asks the same thing as one T leaf (wording may differ; a threshold may differ).
- `narrower`: asks a stricter version of one T leaf (a chart meeting G always meets T, not the reverse).
- `broader`: asks a looser version of one T leaf (a chart meeting T always meets G, not the reverse).
- `negation`: asks the opposite of one T leaf ("no evidence of X" vs "X"; "not secondary to DVT" vs "secondary to
  DVT"), or that none of several T leaves holds ("no contraindications" vs T's separate contraindications: list them
  all). Read polarity from the words, not from where the leaf sits in the tree.
- `part_of`: is one part of a single T leaf that asks several things at once (T: "pain and functional disability";
  G: "pain").
- `combines`: asks, in one leaf, what two or more T leaves ask separately, all of them together ("pain and
  functional disability" vs T's pain and disability; list all of them).
- `any_of`: holds when any one of two or more T leaves holds ("a comorbid condition such as COPD or heart failure"
  vs T's separate COPD and heart-failure leaves; list all of them).
- `none`: no T leaf asks this (an extra requirement, an exclusion, documentation, a different scope).

Rules:
- Every G leaf id appears exactly once. Use only ids shown below, exactly as written (with their T. / G. prefix).
- Match on meaning: the condition, measurement, threshold direction, population and time window. Two leaves about
  the same topic with opposite polarity are `negation`, not `same`.
- A T leaf may be linked from several G leaves, or from none.
- `why`: one short sentence, only when the link is not `same`.

Tree T (answer key):
{{t_tree}}

Tree G (system under test):
{{g_tree}}

T leaves:
{{t_leaves}}

G leaves:
{{g_leaves}}

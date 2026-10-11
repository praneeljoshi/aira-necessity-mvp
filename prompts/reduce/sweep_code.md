Your `tree.json` passes the host's checks. Now do the full-policy sweep and the self-check:

{{sweep}}

Edit `tree.py` for anything the pass finds: you may add conditions and tighten the logic; keep every condition already
in the expression (one you drop is put back). Re-run until it prints OK, then finish with "DONE".

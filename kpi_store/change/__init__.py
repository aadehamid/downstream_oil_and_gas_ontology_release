"""The core that the change commands of KPI Store 1.2 call (KPI-DEC-0002, Q23 step 3).

- approval.py writes and checks the approval record of one change: one JSON file per change (Q4, Q13).
- kgcl.py reads and writes the KGCL lines of the eight statement forms this release applies.
- kpi_tables.py applies parsed changes to the kpi module's tables in a scratch copy of the release, rebuilds the
  module, and turns the difference between two built kpi graphs back into KGCL lines (Q7, item 5).
- reference_items.py does the same for a new reference item, a system or a table, in its own module (Q10, form 5).
- proposal.py reads and writes one proposal folder, suggests its route and finds proposals that conflict (Q5, Q6).

The propose and apply commands (kpi_store/propose.py and kpi_store/apply.py) call these functions. Nothing here
writes outside the folder it is given.
"""


class ChangeRefused(Exception):
    """A change, a KGCL line or an approval record is refused. The message says why in plain words."""

# Proposed retained multi-course reconciliation

This isolated source proposal adds no data and changes no schema, public export,
source permission or current writer adoption. The approved single-course evidence
shape remains unchanged. Saved data review still decides which retained notes
actually establish courses, individual counts and literal names.

The extended evidence shape adds exactly one field to the existing eight:
`course_inventory_digests`, a dictionary of **every** pre-batch linked course ID
to its complete stored-row digest. An empty dictionary asserts an empty inventory.
Each new course must use the same full baseline inventory guard. The transaction
internally excludes only new course IDs inserted earlier in this batch; callers
cannot provide that staging context. Requested baseline inventories are captured before any source or entity mutation.
Every extended addition must match the same captured baseline, and a final check
rejects any change to those preexisting course rows, including an ordinary update
after the last retained addition. An unrelated facility update remains subject
to its ordinary source/row guards and is not globally prohibited. This supports a separately grounded course
at a partially linked facility as well as multiple additions to an empty facility.

The extended shape permits a literal course name or NULL, and a positive integer
individual physical-hole count or NULL. Neither a facility total, subtraction,
course count nor the new guard proves individual identities/counts. Distinct
unnamed courses stay unnamed. Exact names such as Great 28 are not parsed as hole
counts. Unknown individual counts remain NULL even when a facility total is known.
No aggregate parent course, ordered round, component or tee is created implicitly.

Each addition remains operator_defined/golf/address inherit; every other field
must remain NULL. Access, bookability, style, arrival and operational status cannot
be inherited or promoted through this path. This proposal cannot update existing
courses, declare complete facility inventory or classify an unknown putting layout
as obstacle minigolf. Special component/reversible identities still need explicit
representation review; accepted conflicts and held sources remain excluded.

The same facility/retained/note/source digests and complete original support indexes
are required. Blocked source policies and exact URL holds still reject the entire
transaction. A source NULL does not erase known source context. The original support
objects/dates are retained exactly; ledger collection date stays NULL. No permission
is cleared, no source status/date is invented and no retained prose becomes a runtime
fallback. Independent source review and exact factual batch review precede adoption
and authority application. Existing single-course/source/rollback regressions remain.

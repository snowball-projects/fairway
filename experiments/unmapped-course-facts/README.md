# Unfinished unmapped-course facts dialog

This patch preserves the existing three-file local change against historical
base `d505b3d030d133f54b908925db6e5bf03da0263e`. It is not a current-main port.
The original base branch is no longer on GitHub, so this handoff keeps the small
code delta instead of reverting the current app or copying old catalog data.

The proposed dialog exposes known course, tee, optional and access facts without
inventing a coordinate. Selection/filter changes close it and restore focus.
No geocoding, catalog change, API connection or deployment is included.

The exact original delta passed JavaScript syntax checking and all41 supplied
viewport-selection VM cases on its original baseline during extraction. No real
browser/mobile/accessibility check was run. Current main is unchanged.

A contributor should port the dialog and regression cases onto current main,
preserving the newer map-animation cancellation and asset graph behavior. The
patch is source work to continue, not a merge-ready implementation. Original
laptop worktree files are unchanged; no feature was completed for migration.

The diff uses zero context to keep the handoff whitespace-clean. To inspect its
original application, use `git apply --unidiff-zero --check` on the stated base.

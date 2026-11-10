## What and why

<!-- One or two sentences: what this changes and why. Link the issue if there is one. -->

## How it was checked

- [ ] `python3 -m unittest` passes
- [ ] `python3 scripts/build_db.py --sample` and `python3 scripts/verify_db.py --sample` pass
- [ ] If the grammar changed: `reclassify.py` + `blocks_to_md.py` were run, and the full build passes `verify_db.py` (paste the counts before and after)
- [ ] No Markdown was edited by hand; data changes come from the pipeline

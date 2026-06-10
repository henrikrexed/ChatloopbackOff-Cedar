# Regenerate the cedar-agent JSON artifact from the human-editable Cedar source.
# Edit policies.cedar, run `make gen`, commit both files.

.PHONY: gen check

gen:
	python3 gen.py

check:
	python3 gen.py --check

updateOpenAlex:
	python3 scripts/openalex.py

updateEuropePMC:
	python3 scripts/europepmc.py $(ARGS)

.PHONY: updateOpenAlex updateEuropePMC

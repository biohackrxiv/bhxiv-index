updateOpenAlex:
	python3 scripts/openalex.py

updateEuropePMC:
	python3 scripts/europepmc.py $(ARGS)

updateWikidata:
	python3 scripts/wikidata.py $(ARGS)

createQuickstatements:
	python3 scripts/createQuickstatements.py $(ARGS)

cachePdfs:
	python3 scripts/cachePdfs.py $(ARGS)

.PHONY: updateOpenAlex updateEuropePMC updateWikidata createQuickstatements cachePdfs

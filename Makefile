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

extractPdfMetadata:
	python3 scripts/extractPdfMetadata.py $(ARGS)

updateGit:
	python3 scripts/git.py $(ARGS)

findMarkdown:
	python3 scripts/findMarkdown.py $(ARGS)

.PHONY: updateOpenAlex updateEuropePMC updateWikidata createQuickstatements cachePdfs extractPdfMetadata updateGit findMarkdown

serve:
	bundle exec jekyll serve $(ARGS)

updateFromZenodo:
	python3 scripts/updateFromZenodo.py $(ARGS)

updateOpenAlex:
	python3 scripts/openalex.py $(ARGS)

openalexReport:
	python3 scripts/openalexReport.py $(ARGS)

europepmcReport:
	python3 scripts/europepmcReport.py $(ARGS)

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

findFigures:
	python3 scripts/findFigures.py $(ARGS)

checkPdfFigures:
	python3 scripts/checkPdfFigures.py $(ARGS)

exportFigures:
	python3 scripts/exportFigures.py $(ARGS)

setImage:
	python3 scripts/setImage.py $(ARGS)

setDescription:
	python3 scripts/setDescription.py $(ARGS)

.PHONY: serve updateFromZenodo updateOpenAlex openalexReport europepmcReport updateEuropePMC updateWikidata createQuickstatements cachePdfs extractPdfMetadata updateGit findMarkdown findFigures checkPdfFigures exportFigures setImage setDescription

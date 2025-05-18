@Grab(group='io.github.egonw.bacting', module='managers-ui', version='1.0.5')

import groovy.json.JsonSlurper
import java.text.SimpleDateFormat;
import java.util.Date;

workspaceRoot = ".."
ui = new net.bioclipse.managers.UIManager(workspaceRoot);
bioclipse = new net.bioclipse.managers.BioclipseManager(workspaceRoot);

if (args.length < 2) {
  println "Syntax: groovy createPostFromDOI.groovy <BH_CODE> <DOI>"
  System.exit(0)
}

doi = args[1].toLowerCase()
tag = args[0]

localpart = doi.split("/osf.io/")[1].split("_")[0]

bioclipse = new net.bioclipse.managers.BioclipseManager(".")
ui = new net.bioclipse.managers.UIManager(".")

def parser = new JsonSlurper()

metadataContent = bioclipse.download(
  "https://doi.org/" + doi, "application/vnd.citationstyles.csl+json"
)

metadata = parser.parseText(metadataContent)

date = metadata.created."date-time".substring(0,10)

postFile = "/" + date + "-" + localpart + ".markdown"
ui.renewFile(postFile)

header = """---
layout: post
title:  "${metadata.title}"
date:   ${date}
tags: ${tag}
doi: ${doi}
authors:
"""

ui.append(postFile, header)

for (author in metadata.author) {
  ui.append(postFile, "  - name: ${author.given} ${author.family}\n")
  if (author."authenticated-orcid") {
    orcid = author.ORCID.replace("https://orcid.org/","")
    ui.append(postFile, "    orcid: ${orcid}\n")
  }
}

ui.append(postFile, "---\n\n")

ui.append(postFile, metadata."abstract".replace("<p>","").replace("</p>","\n\n"))


import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from pathlib              import Path

from ietfdata.datatracker import *
from pprint import pprint as pp

# =============================================================================
# Example: print the affiliations of the authors
#          of a set of documents

dt = DataTracker(cache_dir=Path("cache"))


def extract_data(doc):
    data = {}

    #import pdb; pdb.set_trace()
    data['title'] = doc.title
    data['time'] = doc.time
    data['affiliation'] = [
        doc_author.affiliation
        for doc_author
        in dt.document_authors(doc)
    ]
    data['group-acronym'] = dt.group(doc.group).acronym
    data['type'] = doc.type.uri

    return data

group = dt.group_from_acronym('mmusic')

drafts = dt.documents(group = group,
                      doctype = dt.document_type(
                          DocumentTypeURI("/api/v1/name/doctypename/draft")))

for i in range(20):
    pp(extract_data(next(drafts)))

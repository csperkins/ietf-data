# Copyright (C) 2017-2019 University of Glasgow
# 
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions 
# are met:
# 
# 1. Redistributions of source code must retain the above copyright notice,
#    this list of conditions and the following disclaimer.
# 
# 2. Redistributions in binary form must reproduce the above copyright
#    notice, this list of conditions and the following disclaimer in the
#    documentation and/or other materials provided with the distribution.
# 
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE
# LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
# CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
# SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
# INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
# CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
# ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.

# The module contains code to interact with the IETF Datatracker
# (https://datatracker.ietf.org/release/about)
#
# The Datatracker API is at https://datatracker.ietf.org/api/v1 and is
# a REST API implemented using Django Tastypie (http://tastypieapi.org)
#
# It's possible to do time range queries on many of these values, for example:
#   https://datatracker.ietf.org/api/v1/person/person/?time__gt=2018-03-27T14:07:36
#
# See also:
#   https://datatracker.ietf.org/api/
#   https://trac.tools.ietf.org/tools/ietfdb/wiki/DatabaseSchemaDescription
#   https://trac.tools.ietf.org/tools/ietfdb/wiki/DatatrackerDrafts
#   RFC 6174 "Definition of IETF Working Group Document States"
#   RFC 6175 "Requirements to Extend the Datatracker for IETF Working Group Chairs and Authors"
#   RFC 6292 "Requirements for a Working Group Charter Tool"
#   RFC 6293 "Requirements for Internet-Draft Tracking by the IETF Community in the Datatracker"
#   RFC 6322 "Datatracker States and Annotations for the IAB, IRTF, and Independent Submission Streams"
#   RFC 6359 "Datatracker Extensions to Include IANA and RFC Editor Processing Information"
#   RFC 7760 "Statement of Work for Extensions to the IETF Datatracker for Author Statistics"

from typing import List, Optional, Tuple, Dict, Iterator

import datetime
import glob
import json
import requests
import unittest
import re

# =================================================================================================================================
# A class to represent the datatracker:

class DataTracker:
    """
    A class for interacting with the IETF DataTracker.
    """
    def __init__(self):
        self.session      = requests.Session()
        self.base_url     = "https://datatracker.ietf.org"


    def __del__(self):
        self.session.close()


    # Datatracker API endpoints returning information about people:
    # * https://datatracker.ietf.org/api/v1/person/person/                  - list of people
    # * https://datatracker.ietf.org/api/v1/person/person/20209/            - info about person 20209
    # * https://datatracker.ietf.org/api/v1/person/email/csp@csperkins.org/ - map from email address to person
    #   https://datatracker.ietf.org/api/v1/person/historicalperson/        - ???
    #   https://datatracker.ietf.org/api/v1/person/historicalemail/         - ???
    #   https://datatracker.ietf.org/api/v1/person/alias/                   - ???

    def email(self, email: str):
        """
        Lookup information about an email address in the datatracker.

        Parameters:
           email : the email address to lookup

        Returns:
            A Dict containing the following fields:
                "resource_uri" -- A URI representing this resource
                "address"      -- The requested email address
                "person"       -- A URI suitable for use with the person() method
                "time"         -- 
                "origin"       -- 
                "primary"      -- True if this is the primary email address of the person
                "active"       -- True if this is an active email address
        """
        response = self.session.get(self.base_url + "/api/v1/person/email/" + email + "/", verify=True)
        if response.status_code == 200:
            return response.json()
        else:
            return None


    def person_from_email(self, email: str):
        """
        Lookup a person in the datatracker based on their email address.

        Parameters:
            email : the email address to lookup

        Returns:
            A Dict containing the same fields as the person() method.
        """
        return self.person("/api/v1/person/email/" + email + "/")


    def person(self, person_uri: str):
        """
        Lookup a Person in the datatracker.

        Parameters:
            person_uri : a URI of the form "/api/v1/person/person/20209/" or "api/v1/person/email/csp@csperkins.org/"

        Returns:
            A Dict containing the following fields:
                "resource_uri"    -- A URI representing this resource
                "id"              -- A unique identifier for the person
                "name"            -- 
                "name_from_draft" -- 
                "ascii"           -- 
                "ascii_short"     -- 
                "user"            -- 
                "time"            -- 
                "photo"           -- URL for a full size photo
                "photo_thumb"     -- URL for a thumbnail photo
                "biography"       -- Biography of the person
                "consent"         -- 
        """
        assert person_uri.startswith("/api/v1/person/")
        assert person_uri.endswith("/")
        if person_uri.startswith("/api/v1/person/person/"):
            response = self.session.get(self.base_url + person_uri, verify=True)
            if response.status_code == 200:
                return response.json()
            else:
                return None
        elif person_uri.startswith("/api/v1/person/email/"):
            response = self.session.get(self.base_url + person_uri, verify=True)
            if response.status_code == 200:
                return self.person(response.json()["person"])
            else:
                return None
        else:
            raise RuntimeError


    def people(self, since="1970-01-01T00:00:00", until="2038-01-19T03:14:07", name_contains=None):
        """
        A generator that returns people recorded in the datatracker. As of April
        2018, there are approximately 21500 people recorded.

        Parameters:
            since         -- Only return people with timestamp after this
            until         -- Only return people with timestamp before this
            name_contains -- Only return peopls whose name containing this string

        Returns:
            An iterator, where each element is as returned by the person() method
        """
        url = self.base_url + "/api/v1/person/person/?time__gt=" + since + "&time__lt=" + until
        if name_contains is not None:
            url = url + "&name__contains=" + name_contains
        while url is not None:
            r = self.session.get(url, verify=True)
            meta = r.json()['meta']
            objs = r.json()['objects']
            url  = meta['next']
            for obj in objs:
                yield obj


    # Datatracker API endpoints returning information about documents:
    # * https://datatracker.ietf.org/api/v1/doc/document/                        - list of documents
    # * https://datatracker.ietf.org/api/v1/doc/document/draft-ietf-avt-rtp-new/ - info about document

    def _derive_document_url(self, doc):
        if doc["type"] == "/api/v1/name/doctypename/agenda/":
            # FIXME: This doesn't work for interim meetings
            # FIXME: This doesn't work for PDF agenda files
            meeting = doc["name"].split("-")[1]
            doc["document_url"] = "https://datatracker.ietf.org/meeting/" + meeting + "/materials/" + doc["uploaded_filename"]
        elif doc["type"] == "/api/v1/name/doctypename/minutes/":
            meeting = doc["name"].split("-")[1]
            doc["document_url"] = "https://datatracker.ietf.org/meeting/" + meeting + "/materials/" + doc["uploaded_filename"]
        elif doc["type"] == "/api/v1/name/doctypename/bluesheets/":
            meeting = doc["name"].split("-")[1]
            doc["document_url"] = "https://www.ietf.org/proceedings/" + meeting + "/bluesheets/" + doc["uploaded_filename"]
        elif doc["type"] == "/api/v1/name/doctypename/charter/":
            doc["document_url"] = "https://www6.ietf.org/charter/"    + doc["name"] + "-" + doc["rev"] + ".txt"
        elif doc["type"] == "/api/v1/name/doctypename/conflrev/":
            doc["document_url"] = "https://www6.ietf.org/cr/"         + doc["name"] + "-" + doc["rev"] + ".txt"
        elif doc["type"] == "/api/v1/name/doctypename/draft/":
            doc["document_url"] = "https://www.ietf.org/archive/id/"  + doc["name"] + "-" + doc["rev"] + ".txt"
        elif doc["type"] == "/api/v1/name/doctypename/slides/":
            meeting = doc["name"].split("-")[1]
            doc["document_url"] = "https://www.ietf.org/proceedings/" + meeting + "/slides/" + doc["uploaded_filename"]
        elif doc["type"] == "/api/v1/name/doctypename/statchg/":
            doc["document_url"] = "https://www6.ietf.org/sc/"         + doc["name"] + "-" + doc["rev"] + ".txt"
        elif doc["type"] == "/api/v1/name/doctypename/liaison/":
            doc["document_url"] = "https://www6.ietf.org/lib/dt/documents/LIAISON/" + doc["uploaded_filename"]
        elif doc["type"] == "/api/v1/name/doctypename/liai-att/":
            doc["document_url"] = "https://www6.ietf.org/lib/dt/documents/LIAISON/" + doc["external_url"]
        elif doc["type"] == "/api/v1/name/doctypename/recording/":
            doc["document_url"] = doc["external_url"]
        elif doc["type"] == "/api/v1/name/doctypename/review/":
            doc["document_url"] = doc["external_url"]
        elif doc["type"] == "/api/v1/name/doctypename/shepwrit/":
            doc["document_url"] = doc["external_url"]
        else:
            raise NotImplementedError


    def document(self, document_uri: str):
        # FIXME: complete documentation
        # FIXME: add method relating to std_level
        # FIXME: add method relating to intended_std_level
        # FIXME: add method relating to submissions
        # FIXME: add method relating to tags
        """
        Lookup metadata about a document in the datatracker.

        Parameters:
            document_uri : a URI of the form "/api/v1/doc/document/draft-ietf-avt-rtp-new/"

        Returns:
            A Dict containing the following fields:
                "resource_uri"      -- A URI representing this resource
                "name"              -- The document name
                "title"             -- The document title
                "pages"             -- The number of pages in the document
                "words"             -- The number of words in the document
                "time"              -- Last modified
                "notify"            -- Email addresses to notify on update or state change
                "expires"           -- Expiration time for the document
                "type"              -- A URI that can be passed to the document_type() method
                "rev"               -- Revision number of the document
                "abstract"          -- The abstract of the document, if present
                "internal_comments" -- 
                "order"             -- 
                "note"              -- 
                "states"            -- A list of URIs that can be passed to the document_state() method
                "ad"                -- A URI that can be passed to the person() method; the responsible area director
                "shepherd"          -- A URI suitable for use with the person() method; the document shepherd
                "group"             -- A URI that can be passed to the group() method
                "stream"            -- A URI that can be passed to the stream() method
                "rfc"               -- RFC number, e.g., "3550", if the document has been published as an RFC
                "std_level"         --
                "intended_std_level -- 
                "submissions"       --
                "tags"              -- 
                "uploaded_filename" -- 
                "external_url"      -- 
                "document_url"      -- A URL to retrieve the document
        """
        assert document_uri.startswith("/api/v1/doc/document/")
        assert document_uri.endswith("/")
        response = self.session.get(self.base_url + document_uri, verify=True)
        if response.status_code == 200:
            doc = response.json()
            assert doc["resource_uri"].startswith("/api/v1/doc/document/")
            assert doc["ad"]       is None or doc["ad"].startswith("/api/v1/person/person")
            assert doc["shepherd"] is None or doc["shepherd"].startswith("/api/v1/person/email")
            self._derive_document_url(doc)
            return doc
        else:
            return None


    def documents(self, since="1970-01-01T00:00:00", until="2038-01-19T03:14:07", doctype=None, group_uri=None):
        """
        A generator that returns JSON objects representing all documents
        recorded in the datatracker. As of 29 April 2018, approximately
        84000 documents are recorded.

        Parameters:
            since     -- Only return people with timestamp after this
            until     -- Only return people with timestamp before this
            doctype   -- Constrain the results to be of type:
                            "agenda"     - Agenda
                            "bluesheets" - Bluesheets
                            "charter"    - Charter
                            "conflrev"   - Conflict Review
                            "draft"      - Draft
                            "liaison"    - Liaison
                            "liai-att"   - Liaison Attachment
                            "minutes"    - Minutes
                            "recording"  - Recording
                            "review"     - Review
                            "shepwrit"   - Shepherd's writeup
                            "slides"     - Slides
                            "statchg"    - Status Change
            group_uri -- Constrain the results to documents from the specified group.

        Returns:
            An iterator, where each element is as returned by the document() method
        """
        url = self.base_url + "/api/v1/doc/document/?time__gt=" + since + "&time__lt=" + until 
        if doctype != None:
            url = url + "&type=" + doctype
        if group_uri != None:
            url = url + "&group=" + group_uri
        while url != None:
            r = self.session.get(url, verify=True)
            meta = r.json()['meta']
            objs = r.json()['objects']
            url  = self.base_url + meta['next']
            for doc in objs:
                assert doc["resource_uri"].startswith("/api/v1/doc/document/")
                assert doc["ad"]       is None or doc["ad"].startswith("/api/v1/person/person")
                assert doc["shepherd"] is None or doc["shepherd"].startswith("/api/v1/person/email")
                self._derive_document_url(doc)
                yield doc


    # Datatracker API endpoints returning information about document aliases:
    # * https://datatracker.ietf.org/api/v1/doc/docalias/rfcXXXX/                - draft that became the given RFC
    #   https://datatracker.ietf.org/api/v1/doc/docalias/bcpXXXX/                - draft that became the given BCP
    #   https://datatracker.ietf.org/api/v1/doc/docalias/stdXXXX/                - RFC that is the given STD

    def document_from_rfc(self, rfc: str):
        """
        Returns the document that became the specified RFC.

        Parameters:
            rfc -- The RFC to lookup, in the form "rfc3550" or "RFC3550"

        Returns:
            A Dict containing the same fields as the document() method.
        """
        assert rfc.lower().startswith("rfc")
        url  = self.base_url + "/api/v1/doc/docalias/" + rfc.lower() + "/"
        response = self.session.get(url, verify=True)
        if response.status_code == 200:
            return self.document(response.json()['document'])
        else:
            return None


    def document_from_bcp(self, bcp: str):
        # FIXME: implement this
        raise NotImplementedError


    def document_from_std(self, std: str):
        # FIXME: implement this
        raise NotImplementedError


    # Datatracker API endpoints returning information about document states:
    # * https://datatracker.ietf.org/api/v1/doc/state/                           - Types of state a document can be in
    # * https://datatracker.ietf.org/api/v1/doc/statetype/                       - Possible types of state for a document

    def document_state(self, state_uri: str):
        """
        Information about the state of a document.

        Parameters:
           state_uri -- A URI representing a document state, e.g., as returned
                        in the states entry of the dict returned by document()

        Returns:
            A Dict containing the following fields:
              id           -- An identifier for the state
              resource_uri -- The URI representing this state
              desc         -- A description of the state
              name         -- The name of the state
              next_states  -- A List of URIs representing possible next states for the document
              order        -- 
              slug         -- Short name
              type         -- A URI as returned by document_state_types()
              used         -- True if this state is used in the datatracker
        """
        assert state_uri.startswith("/api/v1/doc/state/") and state_uri.endswith("/")
        response = self.session.get(self.base_url + state_uri, verify=True)
        if response.status_code == 200:
            return response.json()
        else:
            return None


    def document_states(self, statetype=None):
        """
        A generator returning the possible states a document can be in.

        Parameters:
           statetype -- The 'slug' field from one of the dicts returned by the
                        document_state_types() method; constrains the results
                        to that particular state type.

        Returns:
            A sequence of dicts, as returned by document_state()
        """
        api_url   = "/api/v1/doc/state/"
        if statetype is not None:
            api_url = api_url + "?type=" + statetype
        while api_url != None:
            r = self.session.get(self.base_url + api_url, verify=True)
            meta = r.json()['meta']
            objs = r.json()['objects']
            api_url = meta['next']
            for obj in objs:
                yield obj


    def document_state_types(self):
        """
        A generator returning possible state types for a document.
        These are the possible values of the 'type' field in the 
        output of document_state(), or the statetype parameter to
        document_states().

        Returns:
           A Dict containing the following fields:
              resource_uri -- The URI representing this state
              label        -- A label for the state
              slub         -- A short name for the state

        """
        api_url   = "/api/v1/doc/statetype/"
        while api_url != None:
            r = self.session.get(self.base_url + api_url, verify=True)
            meta = r.json()['meta']
            objs = r.json()['objects']
            api_url = meta['next']
            for obj in objs:
                yield obj


    #   https://datatracker.ietf.org/api/v1/doc/docevent/                        - list of document events
    #   https://datatracker.ietf.org/api/v1/doc/docevent/?doc=...                - events for a document
    #   https://datatracker.ietf.org/api/v1/doc/docevent/?by=...                 - events by a person (as /api/v1/person/person)
    #   https://datatracker.ietf.org/api/v1/doc/docevent/?time=...               - events by time
    #   https://datatracker.ietf.org/api/v1/doc/documentauthor/?document=...     - authors of a document
    #   https://datatracker.ietf.org/api/v1/doc/documentauthor/?person=...       - documents by person (as /api/v1/person/person)
    #   https://datatracker.ietf.org/api/v1/doc/documentauthor/?email=...        - documents by person with particular email
    #   https://datatracker.ietf.org/api/v1/doc/dochistory/
    #   https://datatracker.ietf.org/api/v1/doc/dochistoryauthor/
    #   https://datatracker.ietf.org/api/v1/doc/docreminder/
    #   https://datatracker.ietf.org/api/v1/doc/documenturl/
    #   https://datatracker.ietf.org/api/v1/doc/statedocevent/                   - subset of /api/v1/doc/docevent/; same parameters
    #   https://datatracker.ietf.org/api/v1/doc/ballotdocevent/                  -               "                "
    #   https://datatracker.ietf.org/api/v1/doc/newrevisiondocevent/             -               "                "
    #   https://datatracker.ietf.org/api/v1/doc/submissiondocevent/              -               "                "
    #   https://datatracker.ietf.org/api/v1/doc/writeupdocevent/                 -               "                "
    #   https://datatracker.ietf.org/api/v1/doc/consensusdocevent/               -               "                "
    #   https://datatracker.ietf.org/api/v1/doc/ballotpositiondocevent/          -               "                "
    #   https://datatracker.ietf.org/api/v1/doc/reviewrequestdocevent/           -               "                "
    #   https://datatracker.ietf.org/api/v1/doc/lastcalldocevent/                -               "                "
    #   https://datatracker.ietf.org/api/v1/doc/telechatdocevent/                -               "                "
    #   https://datatracker.ietf.org/api/v1/doc/relateddocument/?source=...      - documents that source draft relates to (references, replaces, etc)
    #   https://datatracker.ietf.org/api/v1/doc/relateddocument/?target=...      - documents that relate to target draft
    #   https://datatracker.ietf.org/api/v1/doc/ballottype/                      - Types of ballot that can be issued on a document
    #   https://datatracker.ietf.org/api/v1/doc/relateddochistory/
    #   https://datatracker.ietf.org/api/v1/doc/initialreviewdocevent/
    #   https://datatracker.ietf.org/api/v1/doc/deletedevent/
    #   https://datatracker.ietf.org/api/v1/doc/addedmessageevent/
    #   https://datatracker.ietf.org/api/v1/doc/editedauthorsdocevent/

    def submission(self, submission):
        # FIXME: add documentation
        """
        Returns a JSON object giving information about a document submission.
        """
        assert submission.startswith("/api/v1/doc/document/")
        assert submission.endswith("/")
        response = self.session.get(self.base_url + submission, verify=True)
        if response.status_code == 200:
            return response.json()
        else:
            return None

    # Datatracker API endpoints returning information about names:
    # * https://datatracker.ietf.org/api/v1/name/doctypename/
    # * https://datatracker.ietf.org/api/v1/name/streamname/
    #   https://datatracker.ietf.org/api/v1/name/dbtemplatetypename/
    #   https://datatracker.ietf.org/api/v1/name/docrelationshipname/
    #   https://datatracker.ietf.org/api/v1/name/doctagname/
    #   https://datatracker.ietf.org/api/v1/name/docurltagname/
    #   https://datatracker.ietf.org/api/v1/name/groupstatename/
    #   https://datatracker.ietf.org/api/v1/name/formallanguagename/
    #   https://datatracker.ietf.org/api/v1/name/timeslottypename/
    #   https://datatracker.ietf.org/api/v1/name/liaisonstatementeventtypename/
    #   https://datatracker.ietf.org/api/v1/name/stdlevelname/
    #   https://datatracker.ietf.org/api/v1/name/ballotpositionname/
    #   https://datatracker.ietf.org/api/v1/name/reviewrequeststatename/
    #   https://datatracker.ietf.org/api/v1/name/groupmilestonestatename/
    #   https://datatracker.ietf.org/api/v1/name/iprlicensetypename/
    #   https://datatracker.ietf.org/api/v1/name/feedbacktypename/
    #   https://datatracker.ietf.org/api/v1/name/reviewtypename/
    #   https://datatracker.ietf.org/api/v1/name/iprdisclosurestatename/
    #   https://datatracker.ietf.org/api/v1/name/reviewresultname/
    #   https://datatracker.ietf.org/api/v1/name/liaisonstatementstate/
    #   https://datatracker.ietf.org/api/v1/name/roomresourcename/
    #   https://datatracker.ietf.org/api/v1/name/liaisonstatementtagname/
    #   https://datatracker.ietf.org/api/v1/name/topicaudiencename/
    #   https://datatracker.ietf.org/api/v1/name/continentname/
    #   https://datatracker.ietf.org/api/v1/name/nomineepositionstatename/
    #   https://datatracker.ietf.org/api/v1/name/importantdatename/
    #   https://datatracker.ietf.org/api/v1/name/liaisonstatementpurposename/
    #   https://datatracker.ietf.org/api/v1/name/constraintname/
    #   https://datatracker.ietf.org/api/v1/name/sessionstatusname/
    #   https://datatracker.ietf.org/api/v1/name/ipreventtypename/
    #   https://datatracker.ietf.org/api/v1/name/agendatypename/
    #   https://datatracker.ietf.org/api/v1/name/docremindertypename/
    #   https://datatracker.ietf.org/api/v1/name/intendedstdlevelname/
    #   https://datatracker.ietf.org/api/v1/name/countryname/
    #   https://datatracker.ietf.org/api/v1/name/meetingtypename/
    #   https://datatracker.ietf.org/api/v1/name/grouptypename/
    #   https://datatracker.ietf.org/api/v1/name/draftsubmissionstatename/
    #   https://datatracker.ietf.org/api/v1/name/rolename/


    def document_type(self, doctype_uri: str):
        # FIXME: add documentation
        assert doctype_uri.startswith("/api/v1/name/doctypename/") and doctype_uri.endswith("/")
        response = self.session.get(self.base_url + doctype_uri, verify=True)
        if response.status_code == 200:
            return response.json()
        else:
            return None


    def document_types(self):
        # FIXME: add documentation
        """
        A generator returning possible document types.
        """
        url = "/api/v1/name/doctypename/"
        while url != None:
            r = self.session.get(self.base_url + url, verify=True)
            meta = r.json()['meta']
            objs = r.json()['objects']
            url  = meta['next']
            for obj in objs:
                yield obj


    def stream(self, stream_uri: str):
        # FIXME: add documentation
        assert stream_uri.startswith("/api/v1/name/streamname/") and stream_uri.endswith("/")
        response = self.session.get(self.base_url + stream_uri, verify=True)
        if response.status_code == 200:
            return response.json()
        else:
            return None


    def streams(self):
        # FIXME: add documentation
        """
        A generator returning possible document streams.
        """
        url = "/api/v1/name/streamname/"
        while url != None:
            r = self.session.get(self.base_url + url, verify=True)
            meta = r.json()['meta']
            objs = r.json()['objects']
            url  = meta['next']
            for obj in objs:
                yield obj


    # Datatracker API endpoints returning information about working groups:
    #   https://datatracker.ietf.org/api/v1/group/group/                               - list of groups
    #   https://datatracker.ietf.org/api/v1/group/group/2161/                          - info about group 2161
    #   https://datatracker.ietf.org/api/v1/group/grouphistory/?group=2161             - history
    #   https://datatracker.ietf.org/api/v1/group/groupurl/?group=2161                 - URLs
    #   https://datatracker.ietf.org/api/v1/group/groupevent/?group=2161               - events
    #   https://datatracker.ietf.org/api/v1/group/groupmilestone/?group=2161           - Current milestones
    #   https://datatracker.ietf.org/api/v1/group/groupmilestonehistory/?group=2161    - Previous milestones
    #   https://datatracker.ietf.org/api/v1/group/milestonegroupevent/?group=2161      - changed milestones
    #   https://datatracker.ietf.org/api/v1/group/role/?group=2161                     - The current WG chairs and ADs of a group
    #   https://datatracker.ietf.org/api/v1/group/role/?person=20209                   - Groups a person is currently involved with
    #   https://datatracker.ietf.org/api/v1/group/role/?email=csp@csperkins.org        - Groups a person is currently involved with
    #   https://datatracker.ietf.org/api/v1/group/rolehistory/?group=2161              - The previous WG chairs and ADs of a group
    #   https://datatracker.ietf.org/api/v1/group/rolehistory/?person=20209            - Groups person was previously involved with
    #   https://datatracker.ietf.org/api/v1/group/rolehistory/?email=csp@csperkins.org - Groups person was previously involved with
    #   https://datatracker.ietf.org/api/v1/group/changestategroupevent/?group=2161    - Group state changes
    #   https://datatracker.ietf.org/api/v1/group/groupstatetransitions                - ???

    def group(self, group_id):
        # FIXME: implement this
        raise NotImplementedError

    def group_from_acronym(self, acronym):
        # FIXME: add documentation
        api_url  = "/api/v1/group/group/?acronym=" + acronym
        response = self.session.get(self.base_url + api_url, verify=True)
        if response.status_code == 200:
            return response.json()["objects"][0]
        else:
            return None

    def groups(self, since="1970-01-01T00:00:00", until="2038-01-19T03:14:07", name_contains=None):
        # FIXME: add documentation
        # FIXME: no tests for this
        """
        A generator that returns JSON objects representing all groups recorded
        in the datatracker. The since and until parameters can be used to contrain
        the output to only entries with timestamps in a particular time range.
        If provided, name_contains filters based on the whether the name field
        contains the specified value.
        """
        api_url = "/api/v1/group/group/?time__gt=" + since + "&time__lt=" + until
        if name_contains != None:
            api_url = api_url + "&name__contains=" + name_contains
        while api_url != None:
            r = self.session.get(self.base_url + api_url, verify=True)
            meta = r.json()['meta']
            objs = r.json()['objects']
            api_url = meta['next']
            for obj in objs:
                yield obj

    # Datatracker API endpoints returning information about meetings:
    #   https://datatracker.ietf.org/api/v1/meeting/meeting/                        - list of meetings
    #   https://datatracker.ietf.org/api/v1/meeting/meeting/747/                    - information about meeting number 747
    #   https://datatracker.ietf.org/api/v1/meeting/session/                        - list of all sessions in meetings
    #   https://datatracker.ietf.org/api/v1/meeting/session/25886/                  - a session in a meeting
    #   https://datatracker.ietf.org/api/v1/meeting/session/?meeting=747            - sessions in meeting number 747
    #   https://datatracker.ietf.org/api/v1/meeting/session/?meeting=747&group=2161 - sessions in meeting number 747 for group 2161
    #   https://datatracker.ietf.org/api/v1/meeting/schedtimesessassignment/59003/  - a schededuled session within a meeting
    #   https://datatracker.ietf.org/api/v1/meeting/timeslot/9480/                  - a time slot within a meeting (time, duration, location)
    #   https://datatracker.ietf.org/api/v1/meeting/schedule/791/                   - a draft of the meeting agenda
    #   https://datatracker.ietf.org/api/v1/meeting/room/537/                       - a room at a meeting
    #   https://datatracker.ietf.org/api/v1/meeting/floorplan/14/                   - floor plan for a meeting venue
    #   ...

# =================================================================================================================================
# Unit tests:

class TestDatatracker(unittest.TestCase):
    def test_email(self):
        dt = DataTracker()
        e  = dt.email("csp@csperkins.org")
        self.assertEqual(e["resource_uri"], "/api/v1/person/email/csp@csperkins.org/")
        self.assertEqual(e["address"],      "csp@csperkins.org")
        self.assertEqual(e["person"],       "/api/v1/person/person/20209/")
        self.assertEqual(e["time"],         "1970-01-01T23:59:59")
        self.assertEqual(e["origin"],       "author: draft-ietf-mmusic-rfc4566bis")
        self.assertEqual(e["primary"],      True)
        self.assertEqual(e["active"],       True)


    def test_person_from_email(self):
        dt = DataTracker()
        p  = dt.person_from_email("csp@csperkins.org")
        self.assertEqual(p["resource_uri"], "/api/v1/person/person/20209/")


    def test_person_person(self):
        dt = DataTracker()
        p  = dt.person("/api/v1/person/person/20209/")
        self.assertEqual(p["id"],              20209)
        self.assertEqual(p["resource_uri"],    "/api/v1/person/person/20209/")
        self.assertEqual(p["name"],            "Colin Perkins")
        self.assertEqual(p["name_from_draft"], "Colin Perkins")
        self.assertEqual(p["ascii"],           "Colin Perkins")
        self.assertEqual(p["ascii_short"],     None)
        self.assertEqual(p["user"],            "")
        self.assertEqual(p["time"],            "2012-02-26T00:03:54")
        self.assertEqual(p["photo"],           "https://www.ietf.org/lib/dt/media/photo/Colin-Perkins-sm.jpg")
        self.assertEqual(p["photo_thumb"],     "https://www.ietf.org/lib/dt/media/photo/Colin-Perkins-sm_PMIAhXi.jpg")
        self.assertEqual(p["biography"],       "Colin Perkins is a Senior Lecturer (Associate Professor) in the School of Computing Science at the University of Glasgow. His research interests are on transport protocols for real-time and interactive multimedia, and on network protocol design, implementation, and specification. He’s been a participant in the IETF and IRTF since 1996, working primarily in the transport area where he co-chairs the RMCAT working group and is a past chair of the AVT and MMUSIC working groups, and in related IRTF research groups. He proposed and co-chaired the first Applied Networking Research Workshop (ANRW), and has been a long-term participant in the Applied Networking Research Prize (ANRP) awarding committee. He received his BEng in Electronic Engineering in 1992, and my PhD in 1996, both from the Department of Electronics at the University of York.")
        self.assertEqual(p["consent"],         True)

    def test_person_email(self):
        dt = DataTracker()
        p  = dt.person("/api/v1/person/email/csp@csperkins.org/")
        self.assertEqual(p["resource_uri"],    "/api/v1/person/person/20209/")


#    def test_people(self):
#        dt = DataTracker()
#        for person in list(dt.people(since="2018-04-01T00:00:00", until="2018-04-30T23:59:59")):
#            print(person["resource_uri"])


    def test_document_draft(self):
        dt = DataTracker()
        d  = dt.document("/api/v1/doc/document/draft-ietf-avt-rtp-new/")
        self.assertEqual(d["resource_uri"], "/api/v1/doc/document/draft-ietf-avt-rtp-new/")
        self.assertEqual(d["time"], "2015-10-14T13:49:52")
        self.assertEqual(d["notify"], "magnus.westerlund@ericsson.com, csp@csperkins.org")
        self.assertEqual(d["expires"], "2003-09-08T00:00:12")
        self.assertEqual(d["type"], "/api/v1/name/doctypename/draft/")
        self.assertEqual(d["rev"], "12")
        self.assertEqual(d["abstract"], "This memorandum describes RTP, the real-time transport protocol.  RTP provides end-to-end network transport functions suitable for applications transmitting real-time data, such as audio, video or simulation data, over multicast or unicast network services.  RTP does not address resource reservation and does not guarantee quality-of- service for real-time services.  The data transport is augmented by a control protocol (RTCP) to allow monitoring of the data delivery in a manner scalable to large multicast networks, and to provide minimal control and identification functionality.  RTP and RTCP are designed to be independent of the underlying transport and network layers.  The protocol supports the use of RTP-level translators and mixers.  Most of the text in this memorandum is identical to RFC 1889 which it obsoletes.  There are no changes in the packet formats on the wire, only changes to the rules and algorithms governing how the protocol is used.  The biggest change is an enhancement to the scalable timer algorithm for calculating when to send RTCP packets in order to minimize transmission in excess of the intended rate when many participants join a session simultaneously. [STANDARDS-TRACK]")
        self.assertEqual(d["internal_comments"], "")
        self.assertEqual(d["states"], ["/api/v1/doc/state/3/", "/api/v1/doc/state/7/"])
        self.assertEqual(d["ad"], "/api/v1/person/person/2515/")
        self.assertEqual(d["group"], "/api/v1/group/group/941/")
        self.assertEqual(d["stream"], "/api/v1/name/streamname/ietf/")
        self.assertEqual(d["rfc"], "3550")
        self.assertEqual(d["intended_std_level"], "/api/v1/name/intendedstdlevelname/std/")
        self.assertEqual(d["resource_uri"], "/api/v1/doc/document/draft-ietf-avt-rtp-new/")
        self.assertEqual(d["std_level"], "/api/v1/name/stdlevelname/std/")
        self.assertEqual(d["external_url"], "")
        self.assertEqual(d["order"], 1)
        self.assertEqual(d["shepherd"], None)
        self.assertEqual(d["note"], "")
        self.assertEqual(d["submissions"], [])
        self.assertEqual(d["tags"], ["/api/v1/name/doctagname/app-min/", "/api/v1/name/doctagname/errata/"])
        self.assertEqual(d["words"], 34861)
        self.assertEqual(d["uploaded_filename"], "")
        self.assertEqual(d["pages"], 104)
        self.assertEqual(d["name"], "draft-ietf-avt-rtp-new")
        self.assertEqual(d["title"], "RTP: A Transport Protocol for Real-Time Applications")
        self.assertEqual(d["document_url"], "https://www.ietf.org/archive/id/draft-ietf-avt-rtp-new-12.txt")
        self.assertEqual(dt.session.get(d["document_url"]).status_code, 200)

    def test_document_agenda(self):
        dt = DataTracker()
        d  = dt.document("/api/v1/doc/document/agenda-90-precis/")
        self.assertEqual(d["resource_uri"],      "/api/v1/doc/document/agenda-90-precis/")
        self.assertEqual(d["document_url"],      "https://datatracker.ietf.org/meeting/90/materials/agenda-90-precis.txt")
        self.assertEqual(d["uploaded_filename"], "agenda-90-precis.txt")
        self.assertEqual(dt.session.get(d["document_url"]).status_code, 200)

    def test_document_minutes(self):
        dt = DataTracker()
        d  = dt.document("/api/v1/doc/document/minutes-89-cfrg/")
        self.assertEqual(d["resource_uri"],      "/api/v1/doc/document/minutes-89-cfrg/")
        self.assertEqual(d["document_url"],      "https://datatracker.ietf.org/meeting/89/materials/minutes-89-cfrg.txt")
        self.assertEqual(d["uploaded_filename"], "minutes-89-cfrg.txt")
        self.assertEqual(dt.session.get(d["document_url"]).status_code, 200)

    def test_document_bluesheets(self):
        dt = DataTracker()
        d  = dt.document("/api/v1/doc/document/bluesheets-95-xrblock-01/")
        self.assertEqual(d["resource_uri"],      "/api/v1/doc/document/bluesheets-95-xrblock-01/")
        self.assertEqual(d["document_url"],      "https://www.ietf.org/proceedings/95/bluesheets/bluesheets-95-xrblock-01.pdf")
        self.assertEqual(d["uploaded_filename"], "bluesheets-95-xrblock-01.pdf")
        self.assertEqual(dt.session.get(d["document_url"]).status_code, 200)

    def test_document_charter(self):
        dt = DataTracker()
        d  = dt.document("/api/v1/doc/document/charter-ietf-vgmib/")
        self.assertEqual(d["resource_uri"],      "/api/v1/doc/document/charter-ietf-vgmib/")
        self.assertEqual(d["document_url"],      "https://www6.ietf.org/charter/charter-ietf-vgmib-01.txt")
        self.assertEqual(d["uploaded_filename"], "")
        self.assertEqual(dt.session.get(d["document_url"]).status_code, 200)

    def test_document_conflrev(self):
        dt = DataTracker()
        d  = dt.document("/api/v1/doc/document/conflict-review-kiyomoto-kcipher2/")
        self.assertEqual(d["resource_uri"],      "/api/v1/doc/document/conflict-review-kiyomoto-kcipher2/")
        self.assertEqual(d["document_url"],      "https://www6.ietf.org/cr/conflict-review-kiyomoto-kcipher2-00.txt")
        self.assertEqual(d["uploaded_filename"], "")
        self.assertEqual(dt.session.get(d["document_url"]).status_code, 200)

    def test_document_slides(self):
        dt = DataTracker()
        d  = dt.document("/api/v1/doc/document/slides-65-l2vpn-4/")
        self.assertEqual(d["resource_uri"],      "/api/v1/doc/document/slides-65-l2vpn-4/")
        self.assertEqual(d["document_url"],      "https://www.ietf.org/proceedings/65/slides/l2vpn-4.pdf")
        self.assertEqual(d["uploaded_filename"], "l2vpn-4.pdf")
        self.assertEqual(dt.session.get(d["document_url"]).status_code, 200)

    def test_document_statchg(self):
        dt = DataTracker()
        d  = dt.document("/api/v1/doc/document/status-change-rfc3044-rfc3187-orig-urn-regs-to-historic/")
        self.assertEqual(d["resource_uri"],      "/api/v1/doc/document/status-change-rfc3044-rfc3187-orig-urn-regs-to-historic/")
        self.assertEqual(d["document_url"],      "https://www6.ietf.org/sc/status-change-rfc3044-rfc3187-orig-urn-regs-to-historic-00.txt")
        self.assertEqual(d["uploaded_filename"], "")
        self.assertEqual(dt.session.get(d["document_url"]).status_code, 200)

    def test_document_liaison(self):
        dt = DataTracker()
        d  = dt.document("/api/v1/doc/document/liaison-2012-05-31-3gpp-mmusic-on-rtcp-bandwidth-negotiation-attachment-1/")
        self.assertEqual(d["resource_uri"],      "/api/v1/doc/document/liaison-2012-05-31-3gpp-mmusic-on-rtcp-bandwidth-negotiation-attachment-1/")
        self.assertEqual(d["document_url"],      "https://www6.ietf.org/lib/dt/documents/LIAISON/liaison-2012-05-31-3gpp-mmusic-on-rtcp-bandwidth-negotiation-attachment-1.doc")
        self.assertEqual(d["uploaded_filename"], "liaison-2012-05-31-3gpp-mmusic-on-rtcp-bandwidth-negotiation-attachment-1.doc")
        self.assertEqual(dt.session.get(d["document_url"]).status_code, 200)

    def test_document_liai_att(self):
        #dt = DataTracker()
        #for d in dt.documents(doctype="liai_att"):
        #    print(d)
        # FIXME: implement tests
        raise NotImplementedError

    def test_document_recording(self):
        #dt = DataTracker()
        #for d in dt.documents(doctype="recording"):
        #    print(d)
        # FIXME: implement tests
        raise NotImplementedError

    def test_document_review(self):
        #dt = DataTracker()
        #for d in dt.documents(doctype="review"):
        #    print(d)
        # FIXME: implement tests
        raise NotImplementedError

    def test_document_shepwrit(self):
        #dt = DataTracker()
        #for d in dt.documents(doctype="shepwrit"):
        #    print(d)
        # FIXME: implement tests
        raise NotImplementedError

#    def test_documents(self):
#        dt = DataTracker()
#        documents = list(dt.documents(since="2007-01-01T00:00:00", until="2007-12-31T23:59:59", doctype="draft", group="941"))

    def test_document_from_rfc(self):
        dt = DataTracker()
        d  = dt.document_from_rfc("rfc3550")
        self.assertEqual(d["resource_uri"], "/api/v1/doc/document/draft-ietf-avt-rtp-new/")

    def test_document_state(self):
        dt = DataTracker()
        s = dt.document_state('/api/v1/doc/state/7/')
        self.assertEqual(s['desc'],         'The ID has been published as an RFC.')
        self.assertEqual(s['id'],           7)
        self.assertEqual(s['name'],         'RFC Published')
        self.assertEqual(s['next_states'],  ['/api/v1/doc/state/8/'])
        self.assertEqual(s['order'],        32)
        self.assertEqual(s['resource_uri'], '/api/v1/doc/state/7/')
        self.assertEqual(s['slug'],         'pub')
        self.assertEqual(s['type'],         '/api/v1/doc/statetype/draft-iesg/')
        self.assertEqual(s['used'],         True)

    def test_document_states(self):
        dt = DataTracker()
        states = list(dt.document_states(statetype="draft-rfceditor"))
        self.assertEqual(len(states), 18)
        self.assertEqual(states[ 0]['name'], 'AUTH')
        self.assertEqual(states[ 1]['name'], 'AUTH48')
        self.assertEqual(states[ 2]['name'], 'EDIT')
        self.assertEqual(states[ 3]['name'], 'IANA')
        self.assertEqual(states[ 4]['name'], 'IESG')
        self.assertEqual(states[ 5]['name'], 'ISR')
        self.assertEqual(states[ 6]['name'], 'ISR-AUTH')
        self.assertEqual(states[ 7]['name'], 'REF')
        self.assertEqual(states[ 8]['name'], 'RFC-EDITOR')
        self.assertEqual(states[ 9]['name'], 'TO')
        self.assertEqual(states[10]['name'], 'MISSREF')
        self.assertEqual(states[11]['name'], 'AUTH48-DONE')
        self.assertEqual(states[12]['name'], 'AUTH48-DONE')
        self.assertEqual(states[13]['name'], 'EDIT')
        self.assertEqual(states[14]['name'], 'IANA')
        self.assertEqual(states[15]['name'], 'IESG')
        self.assertEqual(states[16]['name'], 'ISR-AUTH')
        self.assertEqual(states[17]['name'], 'Pending')

    def test_document_state_types(self):
        dt = DataTracker()
        st = list(dt.document_state_types())
        self.assertEqual(len(st), 23)
        self.assertEqual(st[ 0]["slug"], 'draft')
        self.assertEqual(st[ 1]["slug"], 'draft-iesg')
        self.assertEqual(st[ 2]["slug"], 'draft-iana')
        self.assertEqual(st[ 3]["slug"], 'draft-rfceditor')
        self.assertEqual(st[ 4]["slug"], 'draft-stream-ietf')
        self.assertEqual(st[ 5]["slug"], 'draft-stream-irtf')
        self.assertEqual(st[ 6]["slug"], 'draft-stream-ise')
        self.assertEqual(st[ 7]["slug"], 'draft-stream-iab')
        self.assertEqual(st[ 8]["slug"], 'slides')
        self.assertEqual(st[ 9]["slug"], 'minutes')
        self.assertEqual(st[10]["slug"], 'agenda')
        self.assertEqual(st[11]["slug"], 'liai-att')
        self.assertEqual(st[12]["slug"], 'charter')
        self.assertEqual(st[13]["slug"], 'conflrev')
        self.assertEqual(st[14]["slug"], 'draft-iana-action')
        self.assertEqual(st[15]["slug"], 'draft-iana-review')
        self.assertEqual(st[16]["slug"], 'statchg')
        self.assertEqual(st[17]["slug"], 'recording')
        self.assertEqual(st[18]["slug"], 'bluesheets')
        self.assertEqual(st[19]["slug"], 'reuse_policy')
        self.assertEqual(st[20]["slug"], 'review')
        self.assertEqual(st[21]["slug"], 'liaison')
        self.assertEqual(st[22]["slug"], 'shepwrit')

    def test_submission(self):
        # FIXME: implement tests
        raise NotImplementedError

    def test_group_from_acronym(self):
        dt = DataTracker()
        group = dt.group_from_acronym("avt")
        self.assertEqual(group['id'], 941)


if __name__ == '__main__':
    unittest.main()

# =================================================================================================================================
# vim: set tw=0 ai:
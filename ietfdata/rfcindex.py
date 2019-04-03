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

import xml.etree.ElementTree as ET

import requests
import unittest

# ==================================================================================================

class RfcEntry:
    """
      An RFC entry in the rfc-index.xml file. No attempt is made to
      normalise the data included here.

      Attributes:
        doc_id       : String, e.g., "RFC3550"
        title        : String
        authors      : List of strings 
        doi          : String
        stream       : String
        wg           : None or string
        area         : None or string
        curr_status  : String
        publ_status  : String
        day          : None or integer
        month        : String holding the month name
        year         : Integer
        formats      : List of tuples (file format, char count, page count)
        draft        : None or string
        keywords     : List of strings
        updates      : List of strings
        updated_by   : List of strings
        obsoletes    : List of strings
        obsoleted_by : List of strings
        is_also      : List of strings
        see_also     : List of strings
        errata_url   : None or string
        abstract     : None or Element
    """
    def __init__(self, rfc_element):
        # We explicitly set all attributes that are optional in the XML 
        # to None, or to an empty list, so code using this doesn't need 
        # worry about missing attributes.
        self.wg           = None
        self.area         = None
        self.day          = None
        self.errata_url   = None
        self.abstract     = None
        self.draft        = None
        self.authors      = []
        self.keywords     = []
        self.updates      = []
        self.updated_by   = []
        self.obsoletes    = []
        self.obsoleted_by = []
        self.is_also      = []
        self.see_also     = []
        self.formats      = []

        for elem in rfc_element:
            if   elem.tag == "{http://www.rfc-editor.org/rfc-index}doc-id":
                self.doc_id = elem.text
            elif elem.tag == "{http://www.rfc-editor.org/rfc-index}title":
                self.title  = elem.text
            elif elem.tag == "{http://www.rfc-editor.org/rfc-index}doi":
                self.doi = elem.text
            elif elem.tag == "{http://www.rfc-editor.org/rfc-index}stream":
                self.stream = elem.text
            elif elem.tag == "{http://www.rfc-editor.org/rfc-index}wg_acronym":
                self.wg = elem.text
            elif elem.tag == "{http://www.rfc-editor.org/rfc-index}area":
                self.area = elem.text
            elif elem.tag == "{http://www.rfc-editor.org/rfc-index}current-status":
                self.curr_status = elem.text
            elif elem.tag == "{http://www.rfc-editor.org/rfc-index}publication-status":
                self.publ_status = elem.text
            elif elem.tag == "{http://www.rfc-editor.org/rfc-index}author":
                for inner in elem:
                    if   inner.tag == "{http://www.rfc-editor.org/rfc-index}name":
                        self.authors.append(inner.text)
                    elif inner.tag == "{http://www.rfc-editor.org/rfc-index}title":
                        # Ignore <title>...</title> within <author>...</author> tags
                        # (this is normally just "Editor", which isn't useful)
                        pass 
                    else:
                        raise NotImplementedError
            elif elem.tag == "{http://www.rfc-editor.org/rfc-index}date":
                for inner in elem:
                    if   inner.tag == "{http://www.rfc-editor.org/rfc-index}day":
                        # <day>...</day> is only included for 1 April RFCs
                        self.day = int(inner.text)
                    elif inner.tag == "{http://www.rfc-editor.org/rfc-index}month":
                        self.month = inner.text
                    elif inner.tag == "{http://www.rfc-editor.org/rfc-index}year":
                        self.year = int(inner.text)
                    else:
                        raise NotImplementedError
            elif elem.tag == "{http://www.rfc-editor.org/rfc-index}format":
                # Not all formats have pages, and some of those that do don't have a page count
                page_count = None
                char_count = None

                for inner in elem:
                    if   inner.tag == "{http://www.rfc-editor.org/rfc-index}file-format":
                        file_format = inner.text
                    elif inner.tag == "{http://www.rfc-editor.org/rfc-index}char-count":
                        char_count = int(inner.text)
                    elif inner.tag == "{http://www.rfc-editor.org/rfc-index}page-count":
                        page_count = int(inner.text)
                    else:
                        raise NotImplementedError
                self.formats.append((file_format, char_count, page_count))
            elif elem.tag == "{http://www.rfc-editor.org/rfc-index}draft":
                self.draft = elem.text
            elif elem.tag == "{http://www.rfc-editor.org/rfc-index}keywords":
                for inner in elem:
                    if   inner.tag == "{http://www.rfc-editor.org/rfc-index}kw":
                        # Omit empty <kw></kw> 
                        if inner.text != None:
                            self.keywords.append(inner.text)
                    else:
                        raise NotImplementedError
            elif elem.tag == "{http://www.rfc-editor.org/rfc-index}updates":
                for inner in elem:
                    if   inner.tag == "{http://www.rfc-editor.org/rfc-index}doc-id":
                        self.updates.append(inner.text)
                    else:
                        raise NotImplementedError
            elif elem.tag == "{http://www.rfc-editor.org/rfc-index}updated-by":
                for inner in elem:
                    if   inner.tag == "{http://www.rfc-editor.org/rfc-index}doc-id":
                        self.updated_by.append(inner.text)
                    else:
                        raise NotImplementedError
            elif elem.tag == "{http://www.rfc-editor.org/rfc-index}obsoletes":
                for inner in elem:
                    if   inner.tag == "{http://www.rfc-editor.org/rfc-index}doc-id":
                        self.obsoletes.append(inner.text)
                    else:
                        raise NotImplementedError
            elif elem.tag == "{http://www.rfc-editor.org/rfc-index}obsoleted-by":
                for inner in elem:
                    if   inner.tag == "{http://www.rfc-editor.org/rfc-index}doc-id":
                        self.obsoleted_by.append(inner.text)
                    else:
                        raise NotImplementedError
            elif elem.tag == "{http://www.rfc-editor.org/rfc-index}is-also":
                for inner in elem:
                    if   inner.tag == "{http://www.rfc-editor.org/rfc-index}doc-id":
                        self.is_also.append(inner.text)
                    else:
                        raise NotImplementedError
            elif elem.tag == "{http://www.rfc-editor.org/rfc-index}see-also":
                for inner in elem:
                    if   inner.tag == "{http://www.rfc-editor.org/rfc-index}doc-id":
                        self.see_also.append(inner.text)
                    else:
                        raise NotImplementedError
            elif elem.tag == "{http://www.rfc-editor.org/rfc-index}errata-url":
                self.errata_url = elem.text
            elif elem.tag == "{http://www.rfc-editor.org/rfc-index}abstract":
                # The <abstract>...</abstract> contains formatted XML
                self.abstract = elem
            else:
                raise NotImplementedError

    def __str__(self):
        return "RFC {\n" \
             + "      doc_id: " + self.doc_id            + "\n" \
             + "       title: " + self.title             + "\n" \
             + "     authors: " + str(self.authors)      + "\n" \
             + "         doi: " + self.doi               + "\n" \
             + "      stream: " + self.stream            + "\n" \
             + "          wg: " + str(self.wg)           + "\n" \
             + "        area: " + str(self.area)         + "\n" \
             + " curr_status: " + self.curr_status       + "\n" \
             + " publ_status: " + self.publ_status       + "\n" \
             + "         day: " + str(self.day)          + "\n" \
             + "       month: " + self.month             + "\n" \
             + "        year: " + str(self.year)         + "\n" \
             + "     formats: " + str(self.formats)      + "\n" \
             + "       draft: " + str(self.draft)        + "\n" \
             + "    keywords: " + str(self.keywords)     + "\n" \
             + "     updates: " + str(self.updates)      + "\n" \
             + "  updated_by: " + str(self.updated_by)   + "\n" \
             + "   obsoletes: " + str(self.obsoletes)    + "\n" \
             + "obsoleted_by: " + str(self.obsoleted_by) + "\n" \
             + "     is_also: " + str(self.is_also)      + "\n" \
             + "    see_also: " + str(self.see_also)     + "\n" \
             + "  errata_url: " + str(self.errata_url)   + "\n" \
             + "    abstract: " + str(self.abstract)     + "\n" \
             + "}\n"


    def charset(self):
        # Most RFCs are UTF-8, or it's ASCII subset. A few are not. Return
        # an appropriate encoding for the text of this RFC.
        if   (self.doc_id == "RFC0064") or (self.doc_id == "RFC0101") or \
             (self.doc_id == "RFC0177") or (self.doc_id == "RFC0178") or \
             (self.doc_id == "RFC0182") or (self.doc_id == "RFC0227") or \
             (self.doc_id == "RFC0234") or (self.doc_id == "RFC0235") or \
             (self.doc_id == "RFC0237") or (self.doc_id == "RFC0243") or \
             (self.doc_id == "RFC0270") or (self.doc_id == "RFC0282") or \
             (self.doc_id == "RFC0288") or (self.doc_id == "RFC0290") or \
             (self.doc_id == "RFC0292") or (self.doc_id == "RFC0303") or \
             (self.doc_id == "RFC0306") or (self.doc_id == "RFC0307") or \
             (self.doc_id == "RFC0310") or (self.doc_id == "RFC0313") or \
             (self.doc_id == "RFC0315") or (self.doc_id == "RFC0316") or \
             (self.doc_id == "RFC0317") or (self.doc_id == "RFC0323") or \
             (self.doc_id == "RFC0327") or (self.doc_id == "RFC0367") or \
             (self.doc_id == "RFC0369") or (self.doc_id == "RFC0441") or \
             (self.doc_id == "RFC1305"):
            return "iso8859_1"
        elif self.doc_id == "RFC2166":
            return "windows-1252"
        elif (self.doc_id == "RFC2497") or (self.doc_id == "RFC2497") or \
             (self.doc_id == "RFC2557"):
            return "iso8859_1"
        elif self.doc_id == "RFC2708":
            # This RFC is corrupt: line 521 has a byte with value 0xC6 that
            # is clearly intended to be a ' character, but that code point
            # doesn't correspond to ' in any character set I can find. Use
            # ISO 8859-1 which gets all characters right apart from this.
            return "iso8859_1"
        elif self.doc_id == "RFC2875":
            # Both the text and PDF versions of this document have corrupt
            # characters (lines 754 and 926 of the text version). Using 
            # ISO 8859-1 is no more corrupt than the original.
            return "iso8859_1"
        else:
            return "utf-8"


# ==================================================================================================

class RfcNotIssuedEntry:
    """
      An RFC that was not issued in the rfc-index.xml file.

      Attributes:
        doc_id       : String, e.g., "RFC3550"
    """
    def __init__(self, rfc_not_issued_element):
        for elem in rfc_not_issued_element:
            if   elem.tag == "{http://www.rfc-editor.org/rfc-index}doc-id":
                self.doc_id = elem.text
            else:
                raise NotImplementedError

    def __str__(self):
        return "RFC-Not-Issued {\n" \
             + "      doc_id: " + self.doc_id + "\n" \
             + "}\n"

# ==================================================================================================

class BcpEntry:
    """
      A BCP entry in the rfc-index.xml file.

      Attributes:
        doc_id       : String, e.g., "BCP002"
        is_also      : List of strings
    """
    def __init__(self, bcp_element):
        self.is_also = []

        for elem in bcp_element:
            if   elem.tag == "{http://www.rfc-editor.org/rfc-index}doc-id":
                self.doc_id = elem.text
            elif elem.tag == "{http://www.rfc-editor.org/rfc-index}is-also":
                for inner in elem:
                    if   inner.tag == "{http://www.rfc-editor.org/rfc-index}doc-id":
                        self.is_also.append(inner.text)
                    else:
                        raise NotImplementedError
            else:
                raise NotImplementedError

    def __str__(self):
        return "BCP {\n" \
             + "      doc_id: " + self.doc_id        + "\n" \
             + "     is_also: " + str(self.is_also)  + "\n" \
             + "}\n"

# ==================================================================================================

class StdEntry:
    """
      An STD entry in the rfc-index.xml file.

      Attributes:
        doc_id       : String, e.g., "STD0089"
        title        : String
        is_also      : List of strings
    """
    def __init__(self, std_element):
        self.is_also = []

        for elem in std_element:
            if   elem.tag == "{http://www.rfc-editor.org/rfc-index}doc-id":
                self.doc_id = elem.text
            elif elem.tag == "{http://www.rfc-editor.org/rfc-index}title":
                self.title  = elem.text
            elif elem.tag == "{http://www.rfc-editor.org/rfc-index}is-also":
                for inner in elem:
                    if   inner.tag == "{http://www.rfc-editor.org/rfc-index}doc-id":
                        self.is_also.append(inner.text)
                    else:
                        raise NotImplementedError
            else:
                raise NotImplementedError

    def __str__(self):
        return "STD {\n" \
             + "      doc_id: " + self.doc_id       + "\n" \
             + "       title: " + self.title        + "\n" \
             + "     is_also: " + str(self.is_also) + "\n" \
             + "}\n"

# ==================================================================================================

class FyiEntry:
    """
      A FYI entry in the rfc-index.xml file.

      Attributes:
        doc_id       : String, e.g., "FYI0038"
        is_also      : List of strings
    """
    def __init__(self, fyi_element):
        self.is_also = []

        for elem in fyi_element:
            if   elem.tag == "{http://www.rfc-editor.org/rfc-index}doc-id":
                self.doc_id = elem.text
            elif elem.tag == "{http://www.rfc-editor.org/rfc-index}is-also":
                for inner in elem:
                    if   inner.tag == "{http://www.rfc-editor.org/rfc-index}doc-id":
                        self.is_also.append(inner.text)
                    else:
                        raise NotImplementedError
            else:
                raise NotImplementedError

    def __str__(self):
        return "FYI {\n" \
             + "      doc_id: " + self.doc_id       + "\n" \
             + "     is_also: " + str(self.is_also) + "\n" \
             + "}\n"

# ==================================================================================================

class RFCIndex:
    """
    The RFC Index.

    Attributes:
        rfc            : Dictionary of RfcEntry
        rfc_not_issued : Dictionary of RfcNotIssuedEntry
        bcp            : Dictionary of BcpEntry
        std            : Dictionary of StdEntry
        fyi            : Dictionary of FyiEntry
    """
    def __init__(self):
        self.rfc            = {}
        self.rfc_not_issued = {}
        self.bcp            = {}
        self.std            = {}
        self.fyi            = {}

        session  = requests.Session()
        response = session.get("https://www.rfc-editor.org/rfc-index.xml", verify=True)
        if response.status_code != 200:
            print("cannot fetch RFC index")
            return
        session.close()

        for doc in ET.fromstring(response.text):
            if   doc.tag == "{http://www.rfc-editor.org/rfc-index}rfc-entry":
                val = RfcEntry(doc)
                self.rfc[val.doc_id] = val
            elif doc.tag == "{http://www.rfc-editor.org/rfc-index}rfc-not-issued-entry":
                val = RfcNotIssuedEntry(doc)
                self.rfc_not_issued[val.doc_id] = val
            elif doc.tag == "{http://www.rfc-editor.org/rfc-index}bcp-entry":
                val = BcpEntry(doc)
                self.bcp[val.doc_id] = val
            elif doc.tag == "{http://www.rfc-editor.org/rfc-index}std-entry":
                val = StdEntry(doc)
                self.std[val.doc_id] = val
            elif doc.tag == "{http://www.rfc-editor.org/rfc-index}fyi-entry":
                val = FyiEntry(doc)
                self.fyi[val.doc_id] = val
            else:
                raise NotImplementedError

# ==================================================================================================
# Unit tests:

class TestRFCIndex(unittest.TestCase):
    def test_rfc_index(self):
        rfcindex = RFCIndex()
        print(rfcindex.rfc["RFC3550"])

if __name__ == '__main__':
    unittest.main()

# ==================================================================================================

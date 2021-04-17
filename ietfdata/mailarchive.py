# Copyright (C) 2020 University of Glasgow
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

from __future__    import annotations

import hashlib
import json
import re
import requests
import email
import ietfdata.datatracker as dt
import abc
import os
import logging
import gridfs

from datetime      import datetime, timedelta
from typing        import List, Optional, Tuple, Dict, Iterator, Type, TypeVar, Any
from pathlib       import Path
from pymongo       import MongoClient, ASCENDING, ReplaceOne
from email         import policy
from email.message import Message
from imapclient    import IMAPClient

from dataclasses import dataclass

import time

from email_reply_parser import EmailReplyParser

from bs4 import BeautifulSoup

# =================================================================================================
# Private helper functions:

def _parse_archive_url(archive_url:str) -> Tuple[str, str]:
    aa_start = archive_url.find("://mailarchive.ietf.org/arch/msg")
    aa_uri   = archive_url[aa_start+33:].strip()

    mailing_list = aa_uri[:aa_uri.find("/")]
    message_hash = aa_uri[aa_uri.find("/")+1:]

    return (mailing_list, message_hash)


def _clean_email_text(email : Message) -> str:
    try:
        raw_body = email.get_body()
        clean_text_bytes = raw_body.get_payload(decode=True)
        if raw_body.get_content_charset() is not None:
            clean_text = clean_text_bytes.decode(raw_body.get_content_charset())
        else:
            clean_text = clean_text_bytes.decode("utf-8")
        clean_text = BeautifulSoup(clean_text, "lxml").text # this fixes some issues even in text/plain mails
        clean_text_reply = EmailReplyParser.parse_reply(clean_text)
    except:
        clean_text_reply = ""
    return clean_text_reply

# =================================================================================================

@dataclass(frozen=True)
class MailingListMessage:
    list_name     : str
    message_id    : str
    from_addr     : str
    subject       : str
    date          : datetime
    in_reply_to   : str
    references    : str
    body          : str

# =================================================================================================

class MailingList:
    _list_name         : str
    _num_messages      : int
    _last_updated      : datetime
    _archive_urls      : Dict[str, int]
    _msg_metadata      : Dict[int, Dict[str, Any]]
    _cached_metadata   : Dict[str, Dict[str, Any]]

    def __init__(self, db, fs, list_name: str):
        logging.basicConfig(level=os.environ.get("IETFDATA_LOGLEVEL", "INFO"))
        self.log           = logging.getLogger("ietfdata")
        self._list_name    = list_name
        self._db           = db
        self._fs           = fs
        self._num_messages = self._db.messages.find({"list": self._list_name}).count()
        self._archive_urls = {}
        self._threads      = []

        # Rebuild the archived-at cache:
        aa_cache = self._db.aa_cache.find_one({"list": self._list_name})
        if aa_cache:
            self._archive_urls = aa_cache["archive_urls"]
        else:
            self.log.info(F"no archived-at cache for mailing list {self._list_name}")
            for index, msg in self.messages():
                if msg.message["Archived-At"] is not None:
                    self.log.info(F"scan message {self._list_name}/{index:06} for archived-at")
                    list_name, msg_hash = _parse_archive_url(msg.message["Archived-At"])
                    self._archive_urls[msg_hash] = index
            self._db.aa_cache.replace_one({"list" : self._list_name}, {"list" : self._list_name, "archive_urls": self._archive_urls}, upsert=True)


    def name(self) -> str:
        return self._list_name


    def num_messages(self) -> int:
        return self._num_messages


    def raw_message(self, msg_id: int) -> Message:
        cache_metadata = self._db.messages.find_one({"list" : self._list_name, "imap_uid": msg_id})
        if cache_metadata:
            message = email.message_from_bytes(self._fs.get(cache_metadata["gridfs_id"]).read(), policy=policy.default)
        return message


    def message_indices(self) -> List[int]:
        cache_metadata = self._db.messages.find({"list" : self._list_name})
        indices = [message_metadata["imap_uid"] for message_metadata in cache_metadata]
        return sorted(indices)


    def message_from_archive_url(self, archive_url:str) -> MailingListMessage:
        list_name, msg_hash = _parse_archive_url(archive_url)
        assert list_name == self._list_name
        return self.message(self._archive_urls[msg_hash])


    def message(self, msg_id: int) -> MailingListMessage:
        return MailingListMessage(self.raw_message(msg_id), self._msg_metadata[msg_id])


    def messages(self,
                 since : str = "1970-01-01T00:00:00",
                 until : str = "2038-01-19T03:14:07") -> Iterator[MailingListMessage]:
        messages = self._db.messages.find({"list": self._list_name, "timestamp": {"$gt": datetime.strptime(since, "%Y-%m-%dT%H:%M:%S"), "$lt":datetime.strptime(until, "%Y-%m-%dT%H:%M:%S")}})
        for message in messages:
            yield MailingListMessage(self._list_name,
                                     message["headers"].get("Message-ID", message["headers"].get("Message-Id", None)),
                                     message["headers"]["From"],
                                     message["headers"].get("Subject", message["headers".get("subject", None)]),
                                     message["timestamp"],
                                     message["headers"].get("In-Reply-To", None),
                                     message["headers"].get("References", None),
                                     message["body"])


    def update(self, reuse_imap=None) -> List[int]:
        new_msgs = []
        last_keepalive = datetime.now()
        if reuse_imap is None:
            imap = IMAPClient(host='imap.ietf.org', ssl=False, use_uid=True)
            imap.login("anonymous", "anonymous")
        else:
            imap = reuse_imap
        imap.select_folder("Shared Folders/" + self._list_name, readonly=True)

        msg_list  = imap.search()
        msg_fetch = []

        cached_messages = {msg["imap_uid"] : msg for msg in self._db.messages.find({"list": self._list_name})}

        cache_replaces = []

        for msg_id, msg in imap.fetch(msg_list, "RFC822.SIZE").items():
            curr_keepalive = datetime.now()
            if msg_id not in cached_messages:
                msg_fetch.append(msg_id)
            elif cached_messages[msg_id]["size"] != msg[b"RFC822.SIZE"]:
                self.log.warn(F"message size mismatch: {self._list_name}/{msg_id:06d}.msg ({cached_messages[msg_id]['size']} != {msg[b'RFC822.SIZE']})")
                cache_file = self._fs.get(cached_messages[msg_id]["gridfs_id"])
                cache_file.delete()
                self._db.messages.delete_one({"list" : self._list_name, "imap_uid" : msg_id})
                msg_fetch.append(msg_id)

        if len(msg_fetch) > 0:
            for msg_id, msg in imap.fetch(msg_fetch, "RFC822").items():
                cache_file_id = self._fs.put(msg[b"RFC822"])
                e = email.message_from_bytes(msg[b"RFC822"], policy=policy.default)
                if e["Archived-At"] is not None:
                    list_name, msg_hash = _parse_archive_url(e["Archived-At"])
                    self._archive_urls[msg_hash] = msg_id
                self._num_messages += 1
                try:
                    msg_date = email.utils.parsedate(e["Date"]) # type: Optional[Tuple[int, int, int, int, int, int, int, int, int]]
                    if msg_date is not None:
                        timestamp = datetime.fromtimestamp(time.mktime(msg_date))
                    else:
                        timestamp = None
                except:
                    timestamp = None
                try:
                    headers = {name : value for name, value in e.items()}
                except:
                    headers = {}
                cache_replaces.append(ReplaceOne({"list" : self._list_name, "id": msg_id},
                                                 {"list"       : self._list_name,
                                                  "imap_uid"   : msg_id,
                                                  "gridfs_id"  : cache_file_id,
                                                  "size"       : len(msg[b"RFC822"]),
                                                  "timestamp"  : timestamp,
                                                  "headers"    : headers,
                                                  "body"       : _clean_email_text(e)},
                                                 upsert=True))

                if len(cache_replaces) > 1000:
                    self._db.messages.bulk_write(cache_replaces)
                    cache_replaces = []

                curr_keepalive = datetime.now()
                if (curr_keepalive - last_keepalive) > timedelta(seconds=10):
                    self.log.info("imap keepalive")
                    imap.noop()
                    last_keepalive = curr_keepalive

                new_msgs.append(msg_id)

            self._db.aa_cache.replace_one({"list" : self._list_name}, {"list" : self._list_name, "archive_urls": self._archive_urls}, upsert=True)

        if len(cache_replaces) > 0:
            result = self._db.messages.bulk_write(cache_replaces)

        imap.unselect_folder()
        if reuse_imap is None:
            imap.logout()
        self._last_updated = datetime.now()
        return new_msgs


    def last_updated(self) -> datetime:
        return self._last_updated


# =================================================================================================

class MailArchive:
    _mailing_lists : Dict[str,MailingList]


    def __init__(self, mongodb_hostname: str = "localhost", mongodb_port: int = 27017, mongodb_username: Optional[str] = None, mongodb_password: Optional[str] = None):
        logging.basicConfig(level=os.environ.get("IETFDATA_LOGLEVEL", "INFO"))
        self.log            = logging.getLogger("ietfdata")
        self._mailing_lists = {}

        cache_host = os.environ.get('IETFDATA_CACHE_HOST')
        cache_port = os.environ.get('IETFDATA_CACHE_PORT', 27017)
        cache_username = os.environ.get('IETFDATA_CACHE_USER')
        cache_password = os.environ.get('IETFDATA_CACHE_PASSWORD')
        if cache_host is not None:
            mongodb_hostname = cache_host
        if cache_port is not None:
            mongodb_port = int(cache_port)
        if cache_username is not None:
            mongodb_username = cache_username
        if cache_password is not None:
            mongodb_password = cache_password

        if mongodb_username is not None:
            self._db = MongoClient(host=mongodb_hostname, port=mongodb_port, username=mongodb_username, password=mongodb_password).ietfdata_mailarchive
        else:
            self._db = MongoClient(host=mongodb_hostname, port=mongodb_port).ietfdata_mailarchive

        self._fs            = gridfs.GridFS(self._db)
        self._db.messages.create_index([('list', ASCENDING), ('imap_uid', ASCENDING)], unique=True)
        self._db.messages.create_index([('list', ASCENDING)], unique=False)
        self._db.messages.create_index([('timestamp', ASCENDING)], unique=False)
        self._db.aa_cache.create_index([('list', ASCENDING)], unique=True)
        self._db.metadata_cache.create_index([('list', ASCENDING)], unique=True)


    def mailing_list_names(self) -> Iterator[str]:
        imap = IMAPClient(host='imap.ietf.org', ssl=False, use_uid=True)
        imap.login("anonymous", "anonymous")
        for (flags, delimiter, name) in imap.list_folders():
            if name != "Shared Folders":
                assert name.startswith("Shared Folders/")
                yield name[15:]
        imap.logout()


    def mailing_list(self, mailing_list_name: str) -> MailingList:
        if not mailing_list_name in self._mailing_lists:
            self._mailing_lists[mailing_list_name] = MailingList(self._db, self._fs, mailing_list_name)
        return self._mailing_lists[mailing_list_name]


    def message_from_archive_url(self, archive_url: str) -> MailingListMessage:
        if "//www.ietf.org/mail-archive/web/" in archive_url:
            # This is a legacy mail archive URL. If we retrieve it, the
            # server should redirect us to the current archive location.
            # Unfortunately this will then fail, because messages in the
            # legacy archive are missing the "Archived-At:" header.
            print(archive_url)
            response = requests.get(archive_url)
            assert "//mailarchive.ietf.org/arch/msg" in response.url
            return self.message_from_archive_url(response.url)
        elif "//mailarchive.ietf.org/arch/msg" in archive_url:
            list_name, _ = _parse_archive_url(archive_url)
            mailing_list = self.mailing_list(list_name)
            return mailing_list.message_from_archive_url(archive_url)
        else:
            raise RuntimeError("Cannot resolve mail archive URL")


    def download_all_messages(self) -> None:
        """
        Download all messages.

        WARNING: as of July 2020, this fetches ~26GBytes of data. Use with care!
        """
        ml_names = list(self.mailing_list_names())
        num_list = len(ml_names)

        imap = IMAPClient(host='imap.ietf.org', ssl=False, use_uid=True)
        imap.login("anonymous", "anonymous")
        for index, ml_name in enumerate(ml_names):
            print(F"Updating list {index+1:4d}/{num_list:4d}: {ml_name} ", end="", flush=True)
            ml = self.mailing_list(ml_name)
            nm = ml.update(reuse_imap=imap)
            print(F"({ml.num_messages()} messages; {len(nm)} new)")
        imap.logout()


    def messages(self,
                 since : str = "1970-01-01T00:00:00",
                 until : str = "2038-01-19T03:14:07") -> Iterator[MailingListMessage]:
        messages = self._db.messages.find({"timestamp": {"$gt": datetime.strptime(since, "%Y-%m-%dT%H:%M:%S"), "$lt":datetime.strptime(until, "%Y-%m-%dT%H:%M:%S")}})
        for message in messages:
            yield MailingListMessage(message["list"],
                                     message["headers"].get("Message-ID", message["headers"].get("Message-Id", None)),
                                     message["headers"].get("From", message["headers"].get("from", None)),
                                     message["headers"].get("Subject", message["headers"].get("subject", None)),
                                     message["timestamp"],
                                     message["headers"].get("In-Reply-To", None),
                                     message["headers"].get("References", None),
                                     message["body"])


# =================================================================================================
# vim: set tw=0 ai:

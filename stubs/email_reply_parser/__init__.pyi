from typing import Any

class EmailReplyParser:
    @staticmethod
    def read(text: Any): ...
    @staticmethod
    def parse_reply(text: Any): ...

class EmailMessage:
    SIG_REGEX: Any = ...
    QUOTE_HDR_REGEX: Any = ...
    QUOTED_REGEX: Any = ...
    HEADER_REGEX: Any = ...
    MULTI_QUOTE_HDR_REGEX: Any = ...
    MULTI_QUOTE_HDR_REGEX_MULTILINE: Any = ...
    fragments: Any = ...
    fragment: Any = ...
    text: Any = ...
    found_visible: bool = ...
    def __init__(self, text: Any) -> None: ...
    lines: Any = ...
    def read(self): ...
    @property
    def reply(self): ...
    def quote_header(self, line: Any): ...

class Fragment:
    signature: bool = ...
    headers: Any = ...
    hidden: bool = ...
    quoted: Any = ...
    lines: Any = ...
    def __init__(self, quoted: Any, first_line: Any, headers: bool = ...) -> None: ...
    def finish(self) -> None: ...
    @property
    def content(self): ...
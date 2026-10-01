"""Download selected, curated Kenney packs. No arbitrary model-supplied URLs."""
from pathlib import Path
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
import tempfile
import time

from .importer import MAX_ARCHIVE_BYTES, import_zip

USER_AGENT = "TakeOne-AssetLibrary/0.1 (local previs asset import)"
ALLOWED_HOSTS = {"kenney.nl", "www.kenney.nl"}


def validate_url(url: str) -> str:
    parts = urlsplit(url)
    if (parts.scheme != "https" or parts.hostname not in ALLOWED_HOSTS
            or parts.username or parts.password or parts.port not in (None, 443)):
        raise ValueError("Only HTTPS downloads from the approved Kenney hosts are allowed")
    return url


class ApprovedRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        validate_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class DownloadLinks(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attributes):
        if tag.lower() != "a":
            return
        for key, value in attributes:
            if key == "href" and value and urlsplit(value).path.lower().endswith(".zip"):
                self.links.append(value)


def discover_zip(page_url: str, html: str) -> str:
    parser = DownloadLinks()
    parser.feed(html)
    candidates = sorted({validate_url(urljoin(page_url, href)) for href in parser.links})
    # Never guess a ZIP URL or select an unrelated paid bundle.
    if len(candidates) != 1:
        raise ValueError("Could not identify exactly one official ZIP. Download the selected free pack manually, then use import-zip.")
    return candidates[0]


def download_pack(root: Path, pack: dict, opener=None) -> dict:
    if pack.get("provider") != "kenney":
        raise ValueError("Automatic download currently supports Kenney only; use import-zip for other CC0 packs")
    opener = opener or build_opener(ApprovedRedirects())
    page_url = validate_url(pack["page_url"])
    request = Request(page_url, headers={"User-Agent": USER_AGENT})
    with opener.open(request, timeout=30) as response:
        raw = response.read(2 * 1024 * 1024 + 1)
        if len(raw) > 2 * 1024 * 1024:
            raise ValueError("Source page exceeds the metadata size limit")
        html = raw.decode("utf-8")
    zip_url = discover_zip(page_url, html)
    request = Request(zip_url, headers={"User-Agent": USER_AGENT})
    with tempfile.TemporaryDirectory(prefix="takeone-download-") as directory:
        archive = Path(directory) / "pack.zip"
        size, started = 0, time.monotonic()
        with opener.open(request, timeout=30) as response, archive.open("xb") as output:
            for chunk in iter(lambda: response.read(1024 * 1024), b""):
                size += len(chunk)
                if size > MAX_ARCHIVE_BYTES or time.monotonic() - started > 600:
                    raise ValueError("Download exceeds the size or timeout limit")
                output.write(chunk)
        return import_zip(root, archive, pack, {
            "method": "official_https", "download_url": zip_url,
            "license_evidence": "curated_official_source_page",
        })

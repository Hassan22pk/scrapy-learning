
import re
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse, unquote

import scrapy
from scrapy.http import FormRequest


class CpucDocketsSpider(scrapy.Spider):
    name = "cpuc_new"
    allowed_domains = ["docs.cpuc.ca.gov"]

    start_urls = [
        "https://docs.cpuc.ca.gov/advancedsearchform.aspx"
    ]

    docket_number = "A1705006"

    custom_settings = {
        "ROBOTSTXT_OBEY": True,
        "DOWNLOAD_DELAY": 2,
        "CONCURRENT_REQUESTS_PER_DOMAIN": 1,
        "COOKIES_ENABLED": True,
        "FEED_EXPORT_ENCODING": "utf-8",
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.filings = []
        self.seen_filings = set()
        self.pages_scraped = 0

        # Docket-level values are left unknown until found in the source.
        self.docket_assignees = []
        self.docket_end_time = None
        self.docket_filed_on = None

    def start_requests(self):
        yield scrapy.Request(
            self.start_urls[0],
            callback=self.parse,
            meta={"cookiejar": "cpuc_session"},
        )

    def parse(self, response):
        """Submit the initial docket search."""

        if not response.xpath("//input[@name='ProcNum']"):
            self.logger.error(
                "Could not find the docket search form. URL: %s",
                response.url,
            )
            return

        yield FormRequest.from_response(
            response,
            formxpath="//form[.//*[@name='ProcNum']]",
            formdata={"ProcNum": self.docket_number},
            callback=self.parse_results,
            meta={
                "cookiejar": response.meta.get(
                    "cookiejar", "cpuc_session"
                )
            },
            dont_filter=True,
        )

    @staticmethod
    def clean_text(values):
        """Join non-empty text fragments into one readable string."""

        return " ".join(
            value.strip()
            for value in values
            if value and value.strip()
        )

    @staticmethod
    def parse_date(value):
        """Normalize MM/DD/YYYY dates to YYYY-MM-DD."""

        if not value:
            return None

        match = re.search(
            r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b",
            value,
        )

        if not match:
            return None

        month, day, year = match.groups()

        try:
            return datetime(
                int(year), int(month), int(day)
            ).date().isoformat()
        except ValueError:
            return None

    @staticmethod
    def filename_from_url(url):
        """Return the decoded filename from a document URL."""

        path = urlparse(url).path
        return unquote(path.rsplit("/", 1)[-1])

    def extract_documents(self, row, response, document_title):
        """Extract supported document links from one filing row."""

        documents = []

        links = row.xpath(
            ".//td[contains(@class, 'ResultLinkTD')]//a[@href]"
        )

        for link in links:
            href = (link.attrib.get("href") or "").strip()

            if not href:
                continue

            source_url = urljoin(response.url, href)
            filename = self.filename_from_url(source_url)

            extension_match = re.search(
                r"\.([a-z0-9]+)$",
                filename,
                flags=re.IGNORECASE,
            )

            if not extension_match:
                continue

            extension = extension_match.group(1).lower()

            # Keep document types relevant to this scraper.
            if extension not in {
                "pdf", "doc", "docx", "xls", "xlsx"
            }:
                continue

            link_title = self.clean_text(
                link.xpath(".//text()").getall()
            )

            documents.append({
                "blob_name": filename,
                "extension": extension,
                "name": filename,
                # The result HTML does not establish this value.
                "ons3": True,
                "source_url": source_url,
                "title": document_title or link_title or None,
            })

        return documents

    def extract_filing_parties(self, description):
        """Extract the party named in a 'filed by ... on DATE' phrase."""

        match = re.search(
            r"\bfiled by\s+(.+?)\s+on\s+"
            r"\d{1,2}/\d{1,2}/\d{4}",
            description,
            flags=re.IGNORECASE,
        )

        if not match:
            return []

        party = match.group(1).strip()

        return [party] if party else []

    def extract_filing(self, row, response):
        """Extract one filing from a result-table row."""

        description = self.clean_text(
            row.xpath(
                ".//td[contains(@class, 'ResultTitleTD')]//text()"
            ).getall()
        )

        filing_type = self.clean_text(
            row.xpath(
                ".//td[contains(@class, 'ResultTypeTD')]//text()"
            ).getall()
        )

        # This is the date shown in the Published Date column.
        published_date = self.clean_text(
            row.xpath(
                ".//td[contains(@class, 'ResultDateTD')]//text()"
            ).getall()
        )

        # The date embedded in the description follows "filed by ... on".
        filing_date_match = re.search(
            r"\bfiled by\s+.+?\s+on\s+"
            r"(\d{1,2}/\d{1,2}/\d{4})",
            description,
            flags=re.IGNORECASE,
        )

        filing_date = (
            self.parse_date(filing_date_match.group(1))
            if filing_date_match
            else None
        )

        document_title = re.split(
            r"\s+Proceeding\s*:",
            description,
            maxsplit=1,
            flags=re.IGNORECASE,
        )[0].strip()

        documents = self.extract_documents(
            row,
            response,
            document_title,
        )

        if not description and not documents:
            return None

        filing_parties = self.extract_filing_parties(
            description
        )

        # Preserve the source's published date in the requested
        # filed_on field for compatibility with your existing output.
        # The actual filing date is logged when it differs.
        filed_on = self.parse_date(published_date)

        if filing_date and filed_on and filing_date != filed_on:
            self.logger.debug(
                "Filing date %s differs from published date %s: %s",
                filing_date,
                filed_on,
                document_title,
            )

        filing = {
            "description": description or None,
            "documents": documents,
            "filed_on": filed_on,
            "filing_parties": filing_parties,
            # These fields are not present in the result-table HTML.
            "source_filing_parties": [],
            "state_id": None,
            "types": [filing_type] if filing_type else [],
        }

        # Use the description and document URLs to avoid duplicates.
        key = (
            description,
            tuple(
                document["source_url"]
                for document in documents
            ),
        )

        if key in self.seen_filings:
            return None

        self.seen_filings.add(key)

        return filing

    def parse_results(self, response):
        """Extract filings and follow the ASP.NET next-page postback."""

        self.pages_scraped += 1

        self.logger.info(
            "Scraping results page %s: %s",
            self.pages_scraped,
            response.url,
        )

        # Save the latest response for debugging.
        with open(
            "cpuc_search_debug.html",
            "w",
            encoding="utf-8",
        ) as file:
            file.write(response.text)

        rows = response.xpath(
            "//table[@id='ResultTable']"
            "/tbody/tr[td[contains(@class, 'ResultTitleTD')]]"
        )

        if not rows:
            # Fallback in case the site omits the tbody element.
            rows = response.xpath(
                "//tr[td[contains(@class, 'ResultTitleTD')]]"
            )

        self.logger.info(
            "Found %s filing rows on page %s",
            len(rows),
            self.pages_scraped,
        )

        for row in rows:
            filing = self.extract_filing(row, response)

            if filing is not None:
                self.filings.append(filing)

        # Continue using the current response's ASP.NET form state.
        next_page = response.xpath(
            "//a[@id='lnkNextPage' "
            "and contains(@href, '__doPostBack')]"
        )

        if next_page:
            cookiejar = response.meta.get(
                "cookiejar", "cpuc_session"
            )

            yield FormRequest.from_response(
                response,
                formname="frmResultList",
                formdata={
                    "__EVENTTARGET": "lnkNextPage",
                    "__EVENTARGUMENT": "",
                },
                callback=self.parse_results,
                meta={"cookiejar": cookiejar},
                dont_click=True,
                dont_filter=True,
            )
            return

        self.logger.info(
            "Finished. Pages: %s; unique filings: %s",
            self.pages_scraped,
            len(self.filings),
        )

        # These fields are not established by the search-result
        # table, so do not invent values for them.
        yield {
            "dockets": [{
                "assignees": self.docket_assignees,
                "crawled_at": datetime.now(
                    timezone.utc
                ).isoformat(),
                "end_time": self.docket_end_time,
                "filed_on": self.docket_filed_on,
                "filings": self.filings,
            }]
        }

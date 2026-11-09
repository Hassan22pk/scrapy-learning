
import re
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse, unquote

import scrapy
from scrapy.http import FormRequest
from scrapy.exceptions import CloseSpider


class CpucDocketsSpider(scrapy.Spider):

    name = "cpuc_dockets"

    allowed_domains = [
        "docs.cpuc.ca.gov",
        "apps.cpuc.ca.gov",
    ]

    start_urls = [
        "https://docs.cpuc.ca.gov/advancedsearchform.aspx"
    ]

    custom_settings = {
        "ROBOTSTXT_OBEY": True,
        "DOWNLOAD_DELAY": 2,
        "CONCURRENT_REQUESTS": 1,
        "CONCURRENT_REQUESTS_PER_DOMAIN": 1,
        "COOKIES_ENABLED": True,
        "FEED_EXPORT_ENCODING": "utf-8",
    }

    def __init__(
        self,
        startdate=None,
        enddate=None,
        *args,
        **kwargs
    ):
        super().__init__(*args, **kwargs)

        if not startdate or not enddate:
            raise ValueError(
                "Both startdate and enddate are required. "
                "Example: -a startdate=10/01/2025 "
                "-a enddate=10/05/2025"
            )

        try:
            self.start_date = datetime.strptime(
                startdate, "%m/%d/%Y"
            ).strftime("%m/%d/%Y")

            self.end_date = datetime.strptime(
                enddate, "%m/%d/%Y"
            ).strftime("%m/%d/%Y")

        except ValueError:
            raise ValueError(
                "Invalid date format. Use MM/DD/YYYY."
            )

        if datetime.strptime(
            self.start_date, "%m/%d/%Y"
        ) > datetime.strptime(
            self.end_date, "%m/%d/%Y"
        ):
            raise ValueError(
                "Start date cannot be after end date."
            )

        self.filings = []
        self.seen_filings = set()
        self.pages_scraped = 0

        self.cookiejar = "cpuc_session"

        self.docket_assignees = []
        self.docket_end_time = None
        self.docket_filed_on = None

    # --------------------------------------------------
    # STEP 1: START REQUEST
    # --------------------------------------------------

    def start_requests(self):

        yield scrapy.Request(
            url=self.start_urls[0],
            callback=self.parse,
            meta={
                "cookiejar": self.cookiejar
            },
            dont_filter=True
        )

    # --------------------------------------------------
    # STEP 2: SUBMIT DATE SEARCH
    # --------------------------------------------------

    def parse(self, response):

        self.logger.info(
            "Searching CPUC filings from %s to %s",
            self.start_date,
            self.end_date
        )

        date_form = response.xpath(
            "//form["
            ".//input[@name='FilingDateFrom'] "
            "and .//input[@name='FilingDateTo']"
            "]"
        )

        if not date_form:
            self.logger.error(
                "Date search fields were not found. "
                "Check the actual search form HTML."
            )
            raise CloseSpider("Date search form not found")

        yield FormRequest.from_response(
            response,
            formxpath=(
                "//form["
                ".//input[@name='FilingDateFrom'] "
                "and .//input[@name='FilingDateTo']"
                "]"
            ),
            formdata={
                "FilingDateFrom": self.start_date,
                "FilingDateTo": self.end_date,
                "SearchButton": "Search",
            },
            callback=self.parse_results,
            meta={
                "cookiejar": response.meta.get("cookiejar", "cpuc_session")
            },
            dont_filter=True
        )

    # --------------------------------------------------
    # HELPER: CLEAN TEXT
    # --------------------------------------------------

    @staticmethod
    def clean_text(values):

        return " ".join(
            value.strip()
            for value in values
            if value and value.strip()
        )

    # --------------------------------------------------
    # HELPER: PARSE DATE
    # --------------------------------------------------

    @staticmethod
    def parse_date(value):

        if not value:
            return None

        match = re.search(
            r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b",
            value
        )

        if not match:
            return None

        month, day, year = match.groups()

        try:
            return datetime(
                int(year),
                int(month),
                int(day)
            ).date().isoformat()

        except ValueError:
            return None

    # --------------------------------------------------
    # HELPER: EXTRACT FILENAME
    # --------------------------------------------------

    @staticmethod
    def filename_from_url(url):

        path = urlparse(url).path

        return unquote(
            path.rsplit("/", 1)[-1]
        )

    # --------------------------------------------------
    # STEP 3: EXTRACT DOCUMENTS
    # --------------------------------------------------

    def extract_documents(
        self,
        row,
        response,
        document_title
    ):

        documents = []

        links = row.xpath(
            ".//td[contains(@class, 'ResultLinkTD')]//a[@href]"
        )

        for link in links:

            href = (
                link.attrib.get("href") or ""
            ).strip()

            if not href:
                continue

            source_url = urljoin(
                response.url,
                href
            )

            filename = self.filename_from_url(
                source_url
            )

            extension_match = re.search(
                r"\.([a-z0-9]+)$",
                filename,
                flags=re.IGNORECASE
            )

            if not extension_match:
                continue

            extension = extension_match.group(1).lower()

            if extension not in {
                "pdf",
                "doc",
                "docx",
                "xls",
                "xlsx"
            }:
                continue

            link_title = self.clean_text(
                link.xpath(".//text()").getall()
            )

            documents.append({

                "blob_name": filename,

                "extension": extension,

                "name": filename,

                # Not established by the result HTML.
                "ons3": True,

                "source_url": source_url,

                "title": (
                    document_title
                    or link_title
                    or None
                )

            })

        return documents

    # --------------------------------------------------
    # HELPER: EXTRACT FILING PARTIES
    # --------------------------------------------------

    def extract_filing_parties(self, description):

        match = re.search(
            r"\bfiled by\s+(.+?)\s+on\s+"
            r"\d{1,2}/\d{1,2}/\d{4}",
            description,
            flags=re.IGNORECASE
        )

        if not match:
            return []

        party = match.group(1).strip()

        return [party] if party else []

    # --------------------------------------------------
    # STEP 4: EXTRACT ONE FILING
    # --------------------------------------------------

    def extract_filing(self, row, response):

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

        published_date = self.clean_text(
            row.xpath(
                ".//td[contains(@class, 'ResultDateTD')]//text()"
            ).getall()
        )

        filing_date_match = re.search(
            r"\bfiled by\s+.+?\s+on\s+"
            r"(\d{1,2}/\d{1,2}/\d{4})",
            description,
            flags=re.IGNORECASE
        )

        filing_date = (
            self.parse_date(
                filing_date_match.group(1)
            )
            if filing_date_match
            else None
        )

        document_title = re.split(
            r"\s+Proceeding\s*:",
            description,
            maxsplit=1,
            flags=re.IGNORECASE
        )[0].strip()

        documents = self.extract_documents(
            row,
            response,
            document_title
        )

        if not description and not documents:
            return None

        filing_parties = self.extract_filing_parties(
            description
        )

        filed_on = self.parse_date(
            published_date
        )

        if filing_date and filed_on and filing_date != filed_on:

            self.logger.debug(
                "Filing date %s differs from published date %s",
                filing_date,
                filed_on
            )

        filing = {

            "description": description or None,

            "documents": documents,

            "filed_on": filed_on,

            "filing_parties": filing_parties,

            "source_filing_parties": [],

            "state_id": None,

            "types": (
                [filing_type]
                if filing_type
                else []
            )

        }

        key = (
            description,
            tuple(
                document["source_url"]
                for document in documents
            )
        )

        if key in self.seen_filings:
            return None

        self.seen_filings.add(key)

        return filing

    # --------------------------------------------------
    # STEP 5: SEARCH RESULTS AND PAGINATION
    # --------------------------------------------------

    def parse_results(self, response):

        self.pages_scraped += 1

        self.logger.info(
            "Scraping results page %s",
            self.pages_scraped
        )

        self.logger.info(
            "Response URL: %s",
            response.url
        )

        # Save latest response for debugging.
        with open(
            "cpuc_search_debug.html",
            "w",
            encoding="utf-8"
        ) as file:
            file.write(response.text)

        rows = response.xpath(
            "//table[@id='ResultTable']"
            "/tbody/tr[td[contains(@class, 'ResultTitleTD')]]"
        )

        if not rows:

            rows = response.xpath(
                "//tr[td[contains(@class, 'ResultTitleTD')]]"
            )

        self.logger.info(
            "Found %s filing rows on page %s",
            len(rows),
            self.pages_scraped
        )

        for row in rows:

            filing = self.extract_filing(
                row,
                response
            )

            if filing is not None:
                self.filings.append(filing)

        # Find Next Page button.
        next_page = response.xpath(
            "//a[@id='lnkNextPage' "
            "and contains(@href, '__doPostBack')]"
        )

        if next_page:

            self.logger.info(
                "Moving to next search results page..."
            )

            cookiejar = response.meta.get(
                "cookiejar",
                self.cookiejar
            )

            yield FormRequest.from_response(
                response,
                formname="frmResultList",
                formdata={
                    "__EVENTTARGET": "lnkNextPage",
                    "__EVENTARGUMENT": "",
                },
                callback=self.parse_results,
                meta={
                    "cookiejar": cookiejar
                },
                dont_click=True,
                dont_filter=True
            )

            return

        # --------------------------------------------------
        # STEP 6: FINISH AND EXPORT
        # --------------------------------------------------

        self.logger.info(
            "Search completed."
        )

        self.logger.info(
            "Total pages scraped: %s",
            self.pages_scraped
        )

        self.logger.info(
            "Total unique filings: %s",
            len(self.filings)
        )

        yield {

            "dockets": [{

                "assignees": self.docket_assignees,

                "crawled_at": datetime.now(
                    timezone.utc
                ).isoformat(),

                "end_time": self.docket_end_time,

                "filed_on": self.docket_filed_on,

                "filings": self.filings

            }]

        }

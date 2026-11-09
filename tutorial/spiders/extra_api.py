import json
from urllib.parse import urlparse

import scrapy


class ExtraCategoriesSpider(scrapy.Spider):
    name = "extra_categories123"
    allowed_domains = ["extra.com"]

    def start_requests(self):
        yield scrapy.Request(
            "https://www.extra.com/en-sa",
            callback=self.parse,
        )

    def parse(self, response):
        seen_urls = set()

        for link in response.css("a[data-id][href]"):
            name = (
                link.attrib.get("data-label-en")
                or link.css("label::text").get()
                or link.css("::text").get()
                or ""
            ).strip()

            href = link.attrib.get("href", "").strip()

            if not name or not href:
                continue

            url = response.urljoin(href)
            path = urlparse(url).path.rstrip("/")

            # Exclude repeated navigation-only links.
            if name.lower().startswith("view all"):
                continue

            # Exclude service pages.
            if path.endswith("/extraservices"):
                continue

            # Keep only eXtra Saudi URLs.
            parsed = urlparse(url)
            if parsed.netloc not in {
                "www.extra.com",
                "extra.com",
            }:
                continue

            # Remove query strings and fragments for deduplication.
            canonical_url = f"{parsed.scheme}://{parsed.netloc}{path}"

            if canonical_url in seen_urls:
                continue

            seen_urls.add(canonical_url)

            yield {
                "category_name": name,
                "category_url": url,
                "category_id": link.attrib.get("data-id"),
                "navigation_level": link.attrib.get("data-level"),
            }
            
            #21705619e273429e5767eea44ccb1ad5
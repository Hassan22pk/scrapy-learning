
import scrapy
from urllib.parse import urlparse


class ExtraCategoriesSpider(scrapy.Spider):
    name = "extra_categories"
    allowed_domains = ["extra.com"]

    start_urls = ["https://www.extra.com/en-sa"]

    def parse(self, response):
        seen_urls = set()

        excluded_paths = (
            "/extraservices",
            "/extracare",
            "/extrarepair",
            "/homemaintenance",
            "/trade-in",
            "/jood/benefits",
        )

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
            parsed = urlparse(url)
            path = parsed.path.rstrip("/").lower()

            # Exclude "View all" navigation links.
            if name.lower().startswith("view all"):
                continue

            # Exclude service-related pages.
            if any(
                path == excluded or path.startswith(excluded + "/")
                for excluded in excluded_paths
            ):
                continue

            # Accept only the eXtra website.
            if parsed.netloc not in {"www.extra.com", "extra.com"}:
                continue

            # Ignore query strings and fragments for deduplication.
            canonical_url = (
                f"{parsed.scheme}://{parsed.netloc}{path}"
            )

            if canonical_url in seen_urls:
                continue

            seen_urls.add(canonical_url)

            yield {
                "category_name": name,
                "category_url": url,
                "category_id": link.attrib.get("data-id"),
                "navigation_level": link.attrib.get("data-level"),
            }

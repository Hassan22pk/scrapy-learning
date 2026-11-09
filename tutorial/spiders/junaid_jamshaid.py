
import scrapy
from urllib.parse import urlsplit, urlunsplit


class JunaidJamshedSpider(scrapy.Spider):
    name = "junaid_jamshed"

    allowed_domains = [
        "junaidjamshed.com",
        "www.junaidjamshed.com",
    ]

    start_urls = [
        "https://www.junaidjamshed.com/"
    ]

    handle_httpstatus_list = [429]

    custom_settings = {
        "ROBOTSTXT_OBEY": True,
        "CONCURRENT_REQUESTS": 1,
        "CONCURRENT_REQUESTS_PER_DOMAIN": 1,
        "DOWNLOAD_DELAY": 8,
        "RANDOMIZE_DOWNLOAD_DELAY": True,
        "AUTOTHROTTLE_ENABLED": True,
        "AUTOTHROTTLE_START_DELAY": 8,
        "AUTOTHROTTLE_MAX_DELAY": 120,
        "RETRY_ENABLED": False,
        "FEED_EXPORT_ENCODING": "utf-8",
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.visited_collections = set()
        self.seen_products = set()

    def parse(self, response):
        if response.status == 429:
            self.logger.warning(
                "Rate limit received for %s. Stopping this branch.",
                response.url,
            )
            return

        self.logger.info(
            "Visiting: %s | Status: %s",
            response.url,
            response.status,
        )

        # Extract products from the current page
        cards = response.xpath(
            "//div[contains(@class, 'hdt-card-product__info')]"
        )

        for card in cards:
            title = card.xpath(
                './/a[contains(@class, "hdt-card-product__title")]'
                '/text()'
            ).get()

            href = card.xpath(
                './/a[contains(@class, "hdt-card-product__title")]'
                '/@href'
            ).get()

            price = card.xpath(
                './/span[contains(@class, "hdt-money")]/text()'
            ).get()

            image = card.xpath(
                'preceding::img[1]/@src'
            ).get()

            if not href or not title:
                continue

            # Build a canonical product URL and deduplicate products
            slug = href.split("/products/")[-1].split("?")[0]
            if not slug:
                continue

            product_url = (
                "https://www.junaidjamshed.com/products/" + slug
            )

            if slug in self.seen_products:
                continue

            self.seen_products.add(slug)

            path_parts = urlsplit(response.url).path.strip("/").split("/")
            category = (
                path_parts[1]
                if len(path_parts) > 1
                and path_parts[0] == "collections"
                else "homepage"
            )

            yield {
                "title": title.strip(),
                "price": price.strip() if price else None,
                "url": product_url,
                "image": response.urljoin(image) if image else None,
                "category": category,
            }

        # Follow the next page of the current collection
        next_page = response.xpath(
            '//a[@rel="next"]/@href'
        ).get()

        if next_page:
            yield response.follow(
                next_page,
                callback=self.parse,
            )

        # Discover other collection pages linked on this page
        collection_links = response.xpath(
            '//a[contains(@href, "/collections/")]/@href'
        ).getall()

        for href in collection_links:
            absolute_url = response.urljoin(href)
            parts = urlsplit(absolute_url)

            # Ignore product links nested under collection URLs
            if "/products/" in parts.path:
                continue

            # Only crawl the official website
            if parts.hostname not in self.allowed_domains:
                continue

            # Remove query strings and fragments from category URLs
            collection_url = urlunsplit((
                parts.scheme,
                parts.netloc,
                parts.path.rstrip("/"),
                "",
                "",
            ))

            if collection_url in self.visited_collections:
                continue

            self.visited_collections.add(collection_url)

            yield scrapy.Request(
                collection_url,
                callback=self.parse,
            )



# import scrapy


# class JunaidJamshedSpider(scrapy.Spider):
#     name = "junaid_jamshed"
#     allowed_domains = ["www.junaidjamshed.com"]

#     start_urls = [
#         "https://www.junaidjamshed.com/collections/womens-new-in"
#     ]

#     handle_httpstatus_list = [429]

#     custom_settings = {
#         "ROBOTSTXT_OBEY": True,
#         "CONCURRENT_REQUESTS": 1,
#         "CONCURRENT_REQUESTS_PER_DOMAIN": 1,
#         "DOWNLOAD_DELAY": 5,
#         "RANDOMIZE_DOWNLOAD_DELAY": True,
#         "AUTOTHROTTLE_ENABLED": True,
#         "AUTOTHROTTLE_START_DELAY": 5,
#         "AUTOTHROTTLE_MAX_DELAY": 60,
#         "RETRY_ENABLED": False,
#     }

#     def parse(self, response):
#         if response.status == 429:
#             retry_after = response.headers.get("Retry-After")

#             self.logger.warning(
#                 "Rate limited by website. Retry-After: %s. "
#                 "Stop and wait before trying again.",
#                 retry_after.decode("utf-8") if retry_after else "not provided",
#             )
#             return

#         self.logger.info("Page status: %s", response.status)

#         products = response.xpath(
#             "//div[contains(@class, 'hdt-card-product__info')]"
#         )

#         self.logger.info("Product cards found: %s", len(products))

#         for product in products:
#             title = product.xpath(
#                 './/a[contains(@class, "hdt-card-product__title")]/text()'
#             ).get()

#             price = product.xpath(
#                 './/span[contains(@class, "hdt-money")]/text()'
#             ).get()

#             url = product.xpath(
#                 './/a[contains(@class, "hdt-card-product__title")]/@href'
#             ).get()

#             if title:
#                 yield {
#                     "title": title.strip(),
#                     "price": price.strip() if price else None,
#                     "url": response.urljoin(url) if url else None,
#                 }

#         next_page = response.xpath(
#             '//a[@rel="next"]/@href'
#         ).get()

#         if next_page:
#             yield response.follow(next_page, callback=self.parse)



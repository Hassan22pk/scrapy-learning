
import scrapy


class NdureSpider(scrapy.Spider):
    name = "ndure"
    allowed_domains = ["ndure.com", "www.ndure.com"]

    start_urls = [
        "https://www.ndure.com/collections/all?page=1"
    ]

    def parse(self, response):
        # Extract product links using XPath
        product_links = response.xpath(
            "//a[contains(@href, '/products/')]/@href"
        ).getall()

        product_links = list(set(product_links))

        self.logger.info(
            "Found %s product links on %s",
            len(product_links),
            response.url,
        )

        for link in product_links:
            yield response.follow(
                link,
                callback=self.parse_product,
            )

        # Try the next collection page
        page = response.meta.get("page", 1)

        if product_links:
            next_page = page + 1

            yield scrapy.Request(
                f"https://www.ndure.com/collections/all?page={next_page}",
                callback=self.parse,
                meta={"page": next_page},
            )

    def parse_product(self, response):
        # 1. Product title
        title = response.xpath(
            "normalize-space((//h1)[1])"
        ).get()

        # 2. Regular price
        regular_price = response.xpath(".//div//span[@class='price-item price-item--regular comp-p']//text()"
            # "normalize-space((//*[contains("
            # "concat(' ', normalize-space(@class), ' '),"
            # " ' price__compare-at ')]"
            # "//*[contains(@class, 'price-item')])[1])"
        ).get().strip()

        # if not regular_price:
        #     regular_price = response.xpath(
        #         "normalize-space((//*[contains(@class,"
        #         " 'price-item--regular')])[1])"
        #     ).get()

        # 3. Sale price
        sale_price = response.xpath("//div//span[@class='price-item price-item--regular reg-pr']//text()"
            # "normalize-space((//*[contains(@class,"
            # " 'price-item--sale')])[1])"
        ).get().strip()

        # Fallback: current displayed price
        # if not sale_price:
        #     sale_price = response.xpath(
        #         "normalize-space((//*[contains(@class,"
        #         " 'price-item--last')])[1])"
        #     ).get()

        # 4. All product image URLs
        images = response.xpath(
            "//product-media-gallery//img/@src | "
            "//div[contains(@class, 'product__media')]//img/@src"
        ).getall()

        # Fallback if the theme uses different image markup
        if not images:
            images = response.xpath(
                "//img[contains(@class, 'product')]/@src"
            ).getall()

        # Convert relative URLs to absolute URLs
        images = list(dict.fromkeys(
            response.urljoin(img)
            for img in images
            if img
        ))

        # 5. Product URL
        yield {
            "title": title,
            "regular_price": regular_price or None,
            "sale_price": sale_price or None,
            "images": images,
            "item_url": response.url,
        }


# class NdureJsonSpider(scrapy.Spider):
#     name = "ndure_json"
#     allowed_domains = ["ndure.com", "www.ndure.com"]

#     async def start(self):
#         url = "https://www.ndure.com/products.json?limit=250&page=1"

#         yield scrapy.Request(
#             url,
#             callback=self.parse_products,
#             meta={"page": 1},
#         )

#     def parse_products(self, response):
#         page = response.meta["page"]

#         self.logger.info(
#             "Page %s returned HTTP %s",
#             page,
#             response.status,
#         )

#         try:
#             data = response.json()
#         except ValueError:
#             self.logger.error(
#                 "Response is not JSON: %s",
#                 response.url,
#             )
#             return

#         products = data.get("products", [])

#         self.logger.info(
#             "Products on page %s: %s",
#             page,
#             len(products),
#         )

#         if not products:
#             self.logger.info("No products found; stopping.")
#             return

#         for product in products:
#             variants = product.get("variants", [])

#             prices = [
#                 float(v["price"])
#                 for v in variants
#                 if v.get("price") is not None
#             ]

#             original_prices = [
#                 float(v["compare_at_price"])
#                 for v in variants
#                 if v.get("compare_at_price") is not None
#             ]

#             images = [
#                 img["src"]
#                 for img in product.get("images", [])
#                 if img.get("src")
#             ]

#             yield {
#                 "title": product.get("title"),
#                 "regular_price": (
#                     max(original_prices)
#                     if original_prices else (
#                         max(prices) if prices else None
#                     )
#                 ),
#                 "sale_price": (
#                     min(prices) if prices else None
#                 ),
#                 "images": images,
#                 "item_url": response.urljoin(
#                     "/products/" + product.get("handle", "")
#                 ),
#             }

#         # Request the next page if this page is full.
#         if len(products) >= 250:
#             next_page = page + 1

#             yield scrapy.Request(
#                 "https://www.ndure.com/products.json"
#                 f"?limit=250&page={next_page}",
#                 callback=self.parse_products,
#                 meta={"page": next_page},
#             )



# class QuotesSpider(scrapy.Spider):
#     name = "ndure"
#     start_urls = [
#         "https://www.ndure.com/collections/men-sneakers-sports-shoes",
#     ]

#     def parse(self, response):
#         for item in response.xpath("//ul[@id='product-grid']/li"):
#             title = item.xpath(".//div[@class='card__content']//h2//a[@href]//text()").get()
#             title = title.strip() if title else None
#             url = item.xpath(".//h2[@class='card__heading h5']/a/@href").get()
#             price = item.xpath(".//div[@class='price__regular']//span[@class='price-item price-item--regular reg-pr']//text()").get(),
#         images = item.xpath(".//img/@src").getall()

#             # Convert relative URLs to absolute URLs
#         images = [response.urljoin(image) for image in images if image.strip()]
#         yield {
#                 "title": title,
#                 "url" : url,
#                 "price" : price,
#                 "image" : images
#             }
#         next_page = response.xpath("//a[@aria-label='Next page']/@href").get()

#         if next_page:
#             yield response.follow(next_page, callback=self.parse)


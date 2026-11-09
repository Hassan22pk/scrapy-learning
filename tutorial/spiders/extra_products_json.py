
import json
import os

import scrapy
from urllib.parse import urlencode, urljoin


class ExtraProductsJsonSpider(scrapy.Spider):
    name = "extra_products_json"

    site_key = "ss-unbxd-auk-extra-saudi-en-prod11541714990488"
    rows = 100

    custom_settings = {
        "DOWNLOAD_DELAY": 1,
        "CONCURRENT_REQUESTS": 1,
        "CONCURRENT_REQUESTS_PER_DOMAIN": 1,
        "RETRY_ENABLED": True,
        "RETRY_TIMES": 3,
        "LOG_LEVEL": "INFO",
        "FEEDS": {
            "extra_products_json.json": {
                "format": "json",
                "encoding": "utf-8",
                "indent": 2,
                "overwrite": True,
            }
        },
    }

    def first_value(self, product, *keys):
        """Return the first available value, handling lists."""
        for key in keys:
            value = product.get(key)

            if value is not None and value != "":
                if isinstance(value, list):
                    return value[0] if value else None
                return value

        return None

    def clean_product(self, product):
        """Return only the requested JSON fields."""
        image_url = self.first_value(product, "imageUrl")
        product_url = self.first_value(
            product, "urlEn", "productUrl"
        )

        return {
            "title": self.first_value(product, "title", "nameEn"),
            "price": self.first_value(
                product,
                "priceValueDiscount",
                "sellingPrice",
                "price",
            ),
            "old_price": self.first_value(product, "wasPrice"),
            "discount_percent": self.first_value(
                product, "priceValueDiscountPercentage"
            ),
            "currency": self.first_value(product, "currency"),
            "brand": self.first_value(product, "brand", "brandEn"),
            "product_code": self.first_value(
                product, "productCode", "uniqueId"
            ),
            "image_url": (
                urljoin("https://www.extra.com", image_url)
                if image_url else None
            ),
            "product_url": (
                urljoin("https://www.extra.com", product_url)
                if product_url else None
            ),
            "categories": self.first_value(
                product, "allCategoriesEn"
            ) or [],
        }

    async def start(self):
        api_key = os.environ.get("UNBXD_API_KEY")

        if not api_key:
            self.logger.error(
                "UNBXD_API_KEY is missing. Set it in your terminal."
            )
            return

        self.seen_codes = set()

        yield self.make_request(api_key, start=0)

    def make_request(self, api_key, start):
        base_url = (
            f"https://search.unbxd.io/{api_key}/"
            f"{self.site_key}/search"
        )

        params = [
            ("q", "*"),
            (
                "filter",
                'sellingOutFastCities_uFilter:"SA-riyadh" OR '
                'inStockCities_uFilter:"SA-riyadh" OR '
                "restockableCities:SA-riyadh",
            ),
            ("rows",  str(self.rows)),
            ("start", str(start)),
            ("version", "V2"),
            ("analytics", "false"),
            ("filter", "type:PRODUCT"),
            ("uid", "uid-scrapy-json"),
        ]

        url = base_url + "?" + urlencode(params)

        return scrapy.Request(
            url,
            callback=self.parse_products,
            cb_kwargs={"api_key": api_key, "start": start},
            headers={"Accept": "application/json"},
            dont_filter=True,
        )

    def parse_products(self, response, api_key, start):
        try:
            data = json.loads(response.text)
        except json.JSONDecodeError:
            self.logger.error(
                "Invalid JSON response at offset %s", start
            )
            return

        result = data.get("response", {})
        products = result.get("products", [])
        total = int(result.get("numberOfProducts", 0))

        self.logger.info(
            "Offset %s: received %s products; total reported: %s",
            start, len(products), total,
        )

        if not products:
            self.logger.warning("No products at offset %s", start)
            return

        for product in products:
            cleaned = self.clean_product(product)
            code = cleaned["product_code"]

            if code is not None:
                code = str(code)
                if code in self.seen_codes:
                    continue
                self.seen_codes.add(code)
                cleaned["product_code"] = code

            yield cleaned

        next_start = start + len(products)

        if next_start < total:
            yield self.make_request(api_key, next_start)
        else:
            self.logger.info("Reached the reported end of results.")

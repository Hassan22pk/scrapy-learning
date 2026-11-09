import scrapy
from scrapy.http import FormRequest
import json


class UbereatslocationSpider(scrapy.Spider):
    name = "ubereats"

    location_search = (
        "https://www.ubereats.com/_p/api/mapsSearchV1"
    )
    delivery_address = (
        "https://www.ubereats.com/_p/api/getDeliveryLocationV1"
    )
    feed_url = (
        "https://www.ubereats.com/_p/api/getFeedV1?localeCode=en-US"
    )

    async def start(self):
        yield FormRequest(
            url=self.location_search,
            formdata={"query": "New York, NY"},
            headers={"x-csrf-token": "x"},
            callback=self.parse_search,
        )

    def parse_search(self, response):
        data = response.json()

        # Get the first location result
        location = data["data"][0]

        place_id = location["id"]
        provider = location["provider"]

        self.logger.info("Place ID: %s", place_id)
        self.logger.info("Provider: %s", provider)

        # Second POST request: delivery location
        yield FormRequest(
            url=self.delivery_address,
            formdata={
                "placeId": place_id,
                "provider": provider,
            },
            headers={
                "x-csrf-token": "x",
            },
            callback=self.parse_delivery,
        )

    def parse_delivery(self, response):
        result = response.json()

        self.logger.info(
            "Delivery response: %s",
            response.text
        )

        if result.get("status") != "success":
            self.logger.error("Delivery location failed")
            return

        yield scrapy.Request(
            url=self.feed_url,
            method='POST',
            body=json.dumps({}),
            headers={
                'Content-Type': 'application/json',
                "x-csrf-token": "x",
            },
            meta={"handle_httpstatus_all": True},
            callback=self.parse_feed,
            dont_filter=True,
        )


    def parse_feed(self, response):
        self.logger.info(
            "Feed HTTP status: %s",
            response.status
        )
        import pdb;pdb.set_trace()
        try:
            result = response.json()
        except ValueError:
            self.logger.error(
                "Feed response is not valid JSON: %s",
                response.text[:2000]
            )
            return

        # Save the complete feed response as a Scrapy item
        yield {
            "feed_response": result
        }



# import scrapy
# from scrapy.http import FormRequest
# import json


# class UbereatslocationSpider(scrapy.Spider):
#     name = "ubereats"

#     location_search = (
#         "https://www.ubereats.com/_p/api/mapsSearchV1"
#     )
#     delivery_address = (
#         "https://www.ubereats.com/_p/api/getDeliveryLocationV1"
#     )

#     async def start(self):
#         yield FormRequest(
#             url=self.location_search,
#             formdata={"query": "New York, NY"},
#             headers={"x-csrf-token": "x"},
#             callback=self.parse_search,
#         )

#     def parse_search(self, response):
#         data = response.json()

#         # Get the first location result
#         location = data["data"][0]

#         place_id = location["id"]
#         provider = location["provider"]

#         self.logger.info("Place ID: %s", place_id)
#         self.logger.info("Provider: %s", provider)

#         # Send the second POST request
#         yield scrapy.Request(
#             url=self.delivery_address,
#             method="POST",
#             body=json.dumps({
#                 "placeId": place_id,
#                 "provider": provider,
#             }),
#             headers={
#                 "Content-Type": "application/json",
#                 "x-csrf-token": "x",
#             },
#             callback=self.parse_delivery,
#         )


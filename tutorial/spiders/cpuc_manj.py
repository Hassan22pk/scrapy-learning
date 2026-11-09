import scrapy
import os

class CpucProceedingDocketSpider(scrapy.Spider):
    name = "cpucfull"
    start_urls = ["https://docs.cpuc.ca.gov/advancedsearchform.aspx"]
    # duplicates
    seen_proceedings = set()
    dockets = []
    #docket data
    
    def __init__(self, startdate=None, enddate=None, *args, **kwargs):
        """Date argument"""
        super().__init__(*args, **kwargs)
        self.start_date = startdate or "10/01/2025"
        self.end_date = enddate or "10/05/2025"
    def parse(self, response):
#         """Date range"""
        yield scrapy.FormRequest.from_response(
            response,
            formdata={
                "FilingDateFrom": self.start_date,
                "FilingDateTo": self.end_date,
                "SearchButton": "Search",
                },
            callback=self.parse_results
            )
    def parse_results(self, response):
        
        rows = response.xpath('//td[@class="ResultTitleTD"]')
        for row in rows:
            texts = [t.strip() for t in row.xpath('.//text()').getall() if t.strip()]
            for t in texts:
                if "Proceeding:" in t:
                    proceeding_number = t.replace("Proceeding:", "").strip()
                    for num in proceeding_number.split(";"):
                        num = num.strip()
                        if num and num not in self.seen_proceedings:
                            self.seen_proceedings.add(num)
                            docket_url =(f"https://apps.cpuc.ca.gov/apex/f?p=401:56:6056676397617::NO:RP,57,RIR:P5_PROCEEDING_SELECT:{num}")
                            yield scrapy.Request(url=docket_url,callback=self.parse_docket,meta={"proceeding_number": num})

        next_page = response.xpath("//a[contains(@href, \"__doPostBack('lnkNextPage'\")]/@href").get()

        if next_page:
            self.logger.info("next page")
            viewstate = response.xpath("//input[@id='__VIEWSTATE']/@value").get()
            viewstategen = response.xpath("//input[@id='__VIEWSTATEGENERATOR']/@value").get()
            eventvalidation = response.xpath("//input[@id='__EVENTVALIDATION']/@value").get()

            formdata = {
                "__EVENTTARGET": "lnkNextPage",
                "__EVENTARGUMENT": "",
                "__VIEWSTATE": viewstate,
                "__VIEWSTATEGENERATOR": viewstategen,
                "__EVENTVALIDATION": eventvalidation,
                }

            yield scrapy.FormRequest(url="https://docs.cpuc.ca.gov/SearchRes.aspx",formdata=formdata,callback=self.parse_results)
        else:
            self.logger.info("No more pages")

    def parse_docket(self, response):
        proceeding_number = response.meta["proceeding_number"]

        filed_by = response.css("#P56_FILED_BY::text").get(default="").strip()
        service_lists = [
            link.strip()
            for link in response.css("#P56_SERVICE_LISTS a::attr(href)").getall()
            if link.strip()
            ]
        industry = response.css("#P56_INDUSTRY::text").get(default="").strip()
        filing_date = response.css("#P56_FILING_DATE::text").get(default="").strip()
        category = response.css("#P56_CATEGORY::text").get(default="").strip()
        status = response.css("#P56_STATUS::text").get(default="").strip()
        description = response.css("#P56_DESCRIPTION::text").get(default="").strip()
        staff = ", ".join
        (
            [s.strip() for s in response.css("#P56_STAFF ::text").getall() if s.strip()]
            )

        docket_data = {
            "proceeding_number": proceeding_number,
            "Filed By": filed_by,
            "Service Lists": service_lists,
            "Industry": industry,
            "Filing Date": filing_date,
            "Category": category,
            "Current Status": status,
            "Description": description,
            "Staff": staff,
            "Documents": [],
            }

        documents_url = response.xpath('//ul/li/a[span[text()="Documents"]]/@href').get()
        if documents_url:
            documents_url = response.urljoin(documents_url)
            yield scrapy.Request(
                url=documents_url,
                callback=self.parse_documents,
                meta={"docket_data": docket_data},)
        else:
            self.dockets.append(docket_data)
            yield docket_data

    def parse_documents(self, response):
        docket_data = response.meta["docket_data"]
        if "Documents" not in docket_data:
            docket_data["Documents"] = []

        rows = response.css("table tbody tr")

        for row in rows:
            if row.css("th"):
                continue

            filing_date = row.css('td[headers="FILING_DATE"]::text').get(default="").strip()
            document_type = row.css('td[headers="DOCUMENT_TYPE"] *::text').get(default="").strip()
            filed_by = row.css('td[headers="FILED_BY"]::text').get(default="").strip()
            description = row.css('td[headers="DESCRIPTION"]::text').get(default="").strip()

            docket_data["Documents"].append(
                {
                    "Filing Date": filing_date,
            "Document Type": document_type,
            "Filed By": filed_by,
            "Description": description,})

        next_page = response.xpath(
                "//a[contains(@href,'__doPostBack') and (contains(text(),'Next') or contains(span/text(),'Next'))]/@href").get()
        if next_page:
            self.logger.info(" Moving to next documents page...")
            viewstate = response.xpath("//input[@id='__VIEWSTATE']/@value").get()
            viewstategen = response.xpath("//input[@id='__VIEWSTATEGENERATOR']/@value").get()
            eventvalidation = response.xpath("//input[@id='__EVENTVALIDATION']/@value").get()
            formdata = {
                "__EVENTTARGET": next_page.split("'")[1],
                "__EVENTARGUMENT": "",
                "__VIEWSTATE": viewstate,
                "__VIEWSTATEGENERATOR": viewstategen,
                "__EVENTVALIDATION": eventvalidation,}
            yield scrapy.FormRequest(url=response.url,formdata=formdata,callback=self.parse_documents,meta={"docket_data": docket_data})
        else:
            self.dockets.append(docket_data)
            yield docket_data
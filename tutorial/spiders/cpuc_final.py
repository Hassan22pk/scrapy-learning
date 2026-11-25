import scrapy
from scrapy.http import FormRequest
from datetime import datetime
import json
import re

class CpucDocketsSpider(scrapy.Spider):
    
    name = "cpuc_spider"
    
    allowed_domains = ["docs.cpuc.ca.gov", "apps.cpuc.ca.gov"]
    page_size = 100

    search_url = "https://docs.cpuc.ca.gov/advancedsearchform.aspx"
    apex_url = "https://apps.cpuc.ca.gov/apex"
    ajax_url = "https://apps.cpuc.ca.gov/apex/wwv_flow.ajax"


    AJAX_ID_RE = re.compile(r'"ajaxIdentifier"\s*:\s*"(UkVHSU9OIFRZUEV[^"]+)"')
    custom_settings = {
                "COOKIES_ENABLED": True,
                "DOWNLOAD_TIMEOUT": 120,
                "RETRY_TIMES": 5,
                "RETRY_HTTP_CODES": [500, 502, 503, 504, 522, 524, 408, 429],
                "CONCURRENT_REQUESTS": 2,
                "CONCURRENT_REQUESTS_PER_DOMAIN": 2,
                "DOWNLOAD_DELAY": 1,}

    def __init__(self, start_date=None, end_date=None, proceeding=None, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.proceeding = proceeding.strip() if proceeding else None

        if not self.proceeding:
            if not start_date or not end_date:
                raise ValueError(
                    "Usage: scrapy crawl cpuc_dockets_new "
                    "-a start_date=MM/DD/YYYY -a end_date=MM/DD/YYYY "
                    "(or -a proceeding=A1704001)"
                    )
            datetime.strptime(start_date, "%m/%d/%Y")
            datetime.strptime(end_date, "%m/%d/%Y")

        self.start_date = start_date
        self.end_date = end_date
        self.seen_proceedings = set()
        
    async def start(self):
        if self.proceeding:
            yield scrapy.Request(
                url=(
                    f"https://apps.cpuc.ca.gov/apex/f?p=401:56:0::NO:"
                    f"RP,57,RIR:P5_PROCEEDING_SELECT:{self.proceeding}"
                ),
                callback=self.parse_proceeding,
                meta={"cookiejar": "search","proceeding_number": self.proceeding})
            return

        yield scrapy.Request(
            url=self.search_url,
            callback=self.parse_search_form,
            ) 

    def parse_search_form(self, response):
        
        yield FormRequest.from_response(
            response,
            formid="frmSearchForm",
            formdata={
                "PubDateFrom": self.start_date,
                "PubDateTo": self.end_date,
                "SearchButton": "Search",
            },
            callback=self.parse_results,
            )

    def parse_results(self, response):

        result_cells = response.xpath('//table[@id="ResultTable"]//td[contains(@class, "ResultTitleTD")]')
        for cell in result_cells:
            text = cell.xpath("string(.)").get(default="").strip()

            if "Proceeding:" not in text:
                continue

            proceeding_text = text.split("Proceeding:", 1)[1]
            possible_numbers = proceeding_text.split(";")

            for number in possible_numbers:

                number = number.strip()

                if not number or number in self.seen_proceedings:
                    continue
                    
                self.seen_proceedings.add(number)
                
                yield scrapy.Request(
                    url=f"{self.apex_url}/f?p=401:56:0::NO:RP,57,RIR:P5_PROCEEDING_SELECT:{number}",
                    meta={"cookiejar": number, "proceeding_number": number},
                    callback=self.parse_proceeding,
                    dont_filter=True)
                
        if result_cells and response.xpath('//a[@id="lnkNextPage"]'):
            yield FormRequest.from_response(
                response,
                formdata={"__EVENTTARGET": "lnkNextPage", "__EVENTARGUMENT": ""},
                dont_click=True,
                callback=self.parse_results,
                dont_filter=True,
            )

    def parse_proceeding(self, response):
        proceeding_number = response.meta["proceeding_number"]

        description = response.xpath("//span[@id='P56_DESCRIPTION']/text()").get(default="").strip()
        major_parties = [party.strip() for party in response.xpath("//span[@id='P56_FILED_BY']/text()").getall() if party.strip()]
        industry = [ind.strip() for ind in response.xpath("//span[@id='P56_INDUSTRY']/text()").getall() if ind.strip()]
        filed_date = response.xpath("//span[@id='P56_FILING_DATE']/text()").get(default="").strip()
        status = response.xpath("//span[@id='P56_STATUS']/text()").get(default="").strip()
        assignees = [value.strip() for value in response.xpath("//span[@id='P56_STAFF']/text()").getall() if value.strip()]
        proceeding_type = response.xpath("//span[@id='P56_CATEGORY']/text()").get(default="").strip()
        

        docket = {
                "assignees" : assignees,
                "crawled_at" : datetime.now().isoformat(),
                "end_time": "",
                "filed_on" : filed_date,
                "filings" : [],
                "industries" : industry,
                "job_id":"",
                "major_parties": major_parties,
                "proceeding_type" : proceeding_type,
                "slug" : f"ca-{proceeding_number.lower()}",
                "source_assignees": [],
                "source_major_parties": [],
                "source_title" : description,
                "source_url" : response.url,
                "spider_name" : "on_demand",
                "start_time" : None,
                "state" : "CA",
                "state_id" : proceeding_number,
                "status" : status,
                "titles": description
            }

        documents_url = (
            f"https://apps.cpuc.ca.gov/apex/f?p=401:57:0::NO:"
            f"RP,56,RIR:P5_PROCEEDING_SELECT:{proceeding_number}")
        
        
        yield scrapy.Request(
            url=documents_url,
            callback=self.parse_documents_page,
            meta={
                "cookiejar": response.meta.get("cookiejar"),
                "docket": docket,
                },
            dont_filter=True
            )
        
    def extract_filings(self, response):
        docket = response.meta["docket"]
        rows = response.xpath(
            '//table[contains(@class, "a-IRR-table")]//tr[td]')

        for row in rows:
            filed_on = row.xpath('./td[@headers="FILING_DATE"]/text()').get(default="").strip()
            document_type = row.xpath('./td[@headers="DOCUMENT_TYPE"]//a//text()').get(default="").strip()
            document_url = row.xpath('./td[@headers="DOCUMENT_TYPE"]//a/@href').get(default="").strip()
            filed_by = row.xpath('./td[@headers="FILED_BY"]/text()').get(default="").strip()
            description = row.xpath('./td[@headers="DESCRIPTION"]/text()').get(default="").strip()
            
            filing = {
                "filed_on": filed_on,
                "type": document_type,
                "source_url": response.urljoin(document_url) if document_url else "",
                "filed_by": filed_by,
                "description": description,
                "documents": []
                }
            
            docket["filings"].append(filing)
            
    def parse_documents_page(self, response):
        docket = response.meta["docket"]
        self.extract_filings(response)
        ctx = response.meta.get("ctx")
        if ctx is None:          
            ajax_id = self.AJAX_ID_RE.search(response.text)
            ctx = {
                "p_instance": response.css("#pInstance::attr(value)").get(),
                "salt": response.css("#pSalt::attr(value)").get(),
                "x01": response.css("input[id$='_worksheet_id']::attr(value)").get(),
                "x02": response.css("input[id$='_report_id']::attr(value)").get(),
                "ajax_id": json.loads(f'"{ajax_id.group(1)}"') if ajax_id else None,
                }
            self.logger.info("ctx: %s", ctx)

        next_btn = response.xpath("//button[@title='Next' and not(@disabled)]")

        if next_btn:
            formdata = {
                "p_flow_id": "401",
                "p_flow_step_id": "57",
                "p_instance": ctx["p_instance"],
                "p_debug": "",
                "p_request": f"PLUGIN={ctx['ajax_id']}",
                "p_widget_name": "worksheet",
                "p_widget_mod": "ACTION",
                "p_widget_action": "PAGE",
                "p_widget_action_mod": next_btn.xpath("./@data-pagination").get(),
                "p_widget_num_return": str(self.page_size),
                "x01": ctx["x01"],
                "x02": ctx["x02"],
                "p_json": json.dumps({"pageItems": None, "salt": ctx["salt"]}),
                }

            yield scrapy.FormRequest(
                url=self.ajax_url,
                formdata=formdata,
                callback=self.parse_documents_page,
                meta={
                    "cookiejar": response.meta["cookiejar"],
                    "docket": docket,
                    "ctx": ctx,
                },
                headers={"X-Requested-With": "XMLHttpRequest"},
                dont_filter=True,)
            return

        yield from self.request_document_details(response, docket)
            
          
    def request_document_details(self, response, docket_state):
        if docket_state.get("docket"):   
            docket = docket_state["docket"]
        else:
            docket = docket_state
            
        cookiejar = response.meta.get("cookiejar", "search")

        filings_with_urls = [f for f in docket["filings"] if f["source_url"]]
        if not filings_with_urls:
            yield docket
            return

        state = {"docket":docket, "pending_details": len(filings_with_urls)}
        

        for filing in filings_with_urls:
            yield scrapy.Request(
                url=filing["source_url"],
                callback=self.parse_document_detail,
                errback=self.detail_errback,
                meta={
                    "cookiejar": cookiejar,
                    "filing": filing,
                    "docket_state": state,
                },
                dont_filter=True,)

    def parse_document_detail(self, response):

        rows = response.xpath('//table[@id="ResultTable"]//tr[td[@class="ResultLinkTD"]//a]')
        filing = response.meta["filing"]
        docket_state = response.meta["docket_state"]
        
        try:
            docket_id = docket_state["docket"]["state_id"]
        except:
            docket_id = docket_state["state_id"]

        for row in rows:

            title = row.xpath('normalize-space(string(./td[@class="ResultTitleTD"]))').get(default="")
            pdf_url = row.xpath('./td[@class="ResultLinkTD"]//a/@href').get(default="").strip()
            published_date = row.xpath('./td[@class="ResultDateTD"]/text()').get(default="").strip()

            if not pdf_url:
                continue

            file_name = pdf_url.rsplit("/", 1)[-1]
            extension = file_name.rsplit(".", 1)[-1]
            document_id = file_name.rsplit(".", 1)[0]
            blob_name = f"CA_{docket_id}_{document_id}.{extension}"

            document = {
                "blob_name": blob_name,
                "extension": extension,
                "name": file_name,
                "ons3": False,
                "source_url": response.urljoin(pdf_url),
                "title": title,
                "publish_date": published_date
                }


            filing["documents"].append(document)

        docket_state["pending_details"] -= 1

        if docket_state["pending_details"] == 0:
            yield docket_state["docket"]
            
        
        
    def detail_errback(self, failure):
        request = failure.request
        docket_state = request.meta["docket_state"]

        self.logger.error(f"Detail request failed: {request.url} ({failure.value!r})")

        docket_state["pending_details"] -= 1
        if docket_state["pending_details"] == 0:
            yield docket_state["docket"]



import json
from pathlib import Path
from json import JSONDecoder

source = Path("extra_products_api_backup.json")
output = Path("extra_products_recovered.json")

text = source.read_text(encoding="utf-8")
decoder = JSONDecoder()

# Scrapy's JSON feed is normally one JSON array.
# Recover complete objects from within that array.
products = []
position = text.find("[")

if position == -1:
    raise ValueError("Could not find the beginning of the JSON array.")

position += 1

while position < len(text):
    # Skip whitespace and commas between objects.
    while position < len(text) and (
        text[position].isspace() or text[position] == ","
    ):
        position += 1

    if position >= len(text) or text[position] == "]":
        break

    try:
        product, end = decoder.raw_decode(text, position)
    except json.JSONDecodeError:
        print("Reached an incomplete or invalid record.")
        break

    if isinstance(product, dict):
        products.append(product)

    position = end

# Remove duplicates using the API's uniqueId, when available.
unique = {}
for product in products:
    key = product.get("uniqueId")
    if key:
        unique[key] = product
    else:
        unique[f"record-{len(unique)}"] = product

recovered = list(unique.values())

output.write_text(
    json.dumps(recovered, ensure_ascii=False, indent=2),
    encoding="utf-8",
)

print("Complete records recovered:", len(products))
print("Unique products recovered:", len(recovered))
print("Saved to:", output)


import json
from pathlib import Path
from urllib.parse import urljoin

INPUT_FILE = Path("extra_products_recovered.json")
OUTPUT_FILE = Path("extra_products_clean.json")

BASE_URL = "https://www.extra.com"

with INPUT_FILE.open(encoding="utf-8") as file:
    products = json.load(file)


def first_value(product, *keys):
    for key in keys:
        value = product.get(key)

        if value is not None and value != "":
            if isinstance(value, list):
                return value[0] if value else None
            return value

    return None

clean_products = []
seen = set()

for product in products:
    code = first_value(product, "productCode", "uniqueId")

    # Remove duplicate product codes.
    if code and code in seen:
        continue
    if code:
        seen.add(code)

    product_url = first_value(product, "urlEn", "productUrl")
    image_url = first_value(product, "imageUrl")

    clean_products.append({
        "title": first_value(product, "title", "nameEn"),
        "price": first_value(
            product, "priceValueDiscount", "sellingPrice", "price"
        ),
        "old_price": first_value(product, "wasPrice"),
        "discount_percent": first_value(
            product, "priceValueDiscountPercentage"
        ),
        "currency": first_value(product, "currency"),
        "brand": first_value(product, "brand", "brandEn"),
        "product_code": code,
        "image_url": (
            urljoin(BASE_URL, image_url) if image_url else None
        ),
        "product_url": (
            urljoin(BASE_URL, product_url) if product_url else None
        ),
        "categories": first_value(
            product, "allCategoriesEn", "categories", "categoryPath"
        ),
    })

with OUTPUT_FILE.open("w", encoding="utf-8") as file:
    json.dump(clean_products, file, ensure_ascii=False, indent=2)

print("Input records:", len(products))
print("Clean records:", len(clean_products))
print("Unique product codes:", len(seen))
print("Saved to:", OUTPUT_FILE)

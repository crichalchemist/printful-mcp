"""Markdown renderers for the MCP surface.

Pure functions from a decoded response body to a string. They perform no I/O,
know nothing about Pydantic, and take the identifiers they print as arguments
because a response body does not always carry the id that was asked for.

`summary.py` beside this module renders the same responses for the CLI, which
wants structured data rather than prose. The two are separate because they have
different readers, not because anyone forgot to unify them.
"""
from __future__ import annotations

from typing import Any, Dict


def product(body: Dict[str, Any]) -> str:
    """One catalog product."""
    lines = [
        f"# {body['name']}",
        f"",
        f"**ID:** {body['id']}",
        f"**Type:** {body['type']}",
        f"**Brand:** {body.get('brand', 'N/A')}",
        f"**Variants:** {body['variant_count']}",
        f"**Status:** {'Discontinued' if body['is_discontinued'] else 'Available'}",
        f"",
    ]
    if body.get('description'):
        lines.extend(["## Description", body['description'], ""])
    if body.get('techniques'):
        lines.append("## Available Techniques")
        for tech in body['techniques']:
            default = " (default)" if tech.get('is_default') else ""
            lines.append(f"- **{tech['display_name']}** ({tech['key']}){default}")
        lines.append("")
    if body.get('placements'):
        lines.append(f"## Placements ({len(body['placements'])} available)")
        for placement in body['placements'][:5]:
            lines.append(f"- {placement['placement']} - {placement['technique']}")
        if len(body['placements']) > 5:
            lines.append(f"  _(and {len(body['placements']) - 5} more)_")
        lines.append("")
    return "\n".join(lines)


def products(data: Dict[str, Any]) -> str:
    """A page of catalog products."""
    rows = data.get('data', [])
    paging = data.get('paging', {})
    lines = [
        f"# Catalog Products ({paging.get('total', 0)} total)",
        f"",
        f"Showing {len(rows)} products (offset: {paging.get('offset', 0)}, "
        f"limit: {paging.get('limit', 20)})",
        f"",
    ]
    for row in rows:
        lines.extend([
            f"## {row['name']}",
            f"- **ID:** {row['id']}",
            f"- **Type:** {row['type']}",
            f"- **Variants:** {row['variant_count']}",
            f"- **Techniques:** {', '.join(t['key'] for t in row.get('techniques', []))}",
            f"",
        ])
    return "\n".join(lines)


def variants(data: Dict[str, Any], product_id: int) -> str:
    """A page of variants for one product.

    `product_id` is an argument because the variants response does not repeat
    the product it belongs to, and the heading names it.
    """
    rows = data.get('data', [])
    paging = data.get('paging', {})
    lines = [
        f"# Variants for Product {product_id}",
        f"",
        f"Total variants: {paging.get('total', 0)}",
        f"Showing {len(rows)} variants",
        f"",
    ]
    for row in rows:
        lines.extend([
            f"## {row['name']}",
            f"- **Variant ID:** {row['id']}",
            f"- **Size:** {row['size']}",
            f"- **Color:** {row['color']} ({row['color_code']})",
            f"",
        ])
    return "\n".join(lines)


def variant_prices(data: Dict[str, Any], variant_id: int) -> str:
    """Pricing for one variant."""
    body = data.get('data', {})
    currency = body.get('currency', 'USD')
    lines = [
        f"# Pricing for Variant {variant_id}",
        f"",
        f"**Currency:** {currency}",
        f"",
    ]
    if body.get('variant', {}).get('techniques'):
        lines.append("## Base Prices by Technique")
        for tech in body['variant']['techniques']:
            lines.append(
                f"- **{tech['technique_display_name']}:** {tech['price']} {currency}")
        lines.append("")
    if body.get('product', {}).get('placements'):
        lines.append("## Additional Placement Prices")
        for placement in body['product']['placements']:
            lines.append(
                f"- **{placement['title']}:** {placement['price']} {currency}")
        lines.append("")
    return "\n".join(lines)


def availability(data: Dict[str, Any], product_id: int) -> str:
    """Stock availability per variant and technique."""
    lines = [f"# Availability for Product {product_id}", f""]
    for row in data.get('data', []):
        lines.append(f"## Variant {row['catalog_variant_id']}")
        for tech in row.get('techniques', []):
            lines.append(f"### {tech['technique']}")
            for region in tech.get('selling_regions', []):
                lines.append(f"- **{region['name']}:** {region['availability']}")
        lines.append("")
    return "\n".join(lines)


def categories(data: Dict[str, Any]) -> str:
    """A page of catalog categories."""
    rows = data.get('data', [])
    paging = data.get('paging', {})
    lines = [
        f"# Catalog Categories ({paging.get('total', 0)} total)",
        f"",
        f"Showing {len(rows)} categories",
        f"",
    ]
    for row in rows:
        parent = row.get('parent_id')
        suffix = f" (parent: {parent})" if parent else ""
        lines.append(f"- **{row['title']}** — ID {row['id']}{suffix}")
    lines.append("")
    return "\n".join(lines)


def category(data: Dict[str, Any]) -> str:
    """One catalog category."""
    body = data.get('data', {})
    lines = [
        f"# {body.get('title', 'Category')}",
        f"",
        f"**ID:** {body.get('id')}",
        f"**Parent ID:** {body.get('parent_id', 'none')}",
        f"",
    ]
    if body.get('image_url'):
        lines.extend([f"**Image:** {body['image_url']}", ""])
    return "\n".join(lines)


def size_guide(data: Dict[str, Any], product_id: int) -> str:
    """The size tables for one product."""
    body = data.get('data', {})
    lines = [
        f"# Size Guide for Product {product_id}",
        f"",
        f"**Unit:** {body.get('unit', 'unknown')}",
        f"",
    ]
    for table in body.get('size_tables', []):
        lines.append(f"## {table.get('type', 'Measurements')}")
        if table.get('description'):
            lines.extend([table['description'], ""])
        for measurement in table.get('measurements', []):
            values = ", ".join(
                f"{v.get('size')}: {v.get('min_value', v.get('value', ''))}"
                f"{'-' + str(v['max_value']) if v.get('max_value') else ''}"
                for v in measurement.get('values', [])
            )
            lines.append(f"- **{measurement.get('type_label', '')}** — {values}")
        lines.append("")
    return "\n".join(lines)


def order(body: Dict[str, Any]) -> str:
    """One order."""
    lines = [
        f"# Order {body['id']}",
        f"",
        f"**Status:** {body['status']}",
        f"**External ID:** {body.get('external_id', 'N/A')}",
        f"**Created:** {body['created_at']}",
        f"**Updated:** {body['updated_at']}",
        f"",
    ]
    if body.get('recipient'):
        recipient = body['recipient']
        lines.extend([
            "## Recipient",
            f"**Name:** {recipient['name']}",
            f"**Address:** {recipient['address1']}",
            f"**City:** {recipient['city']}, {recipient.get('state_code', '')} "
            f"{recipient['zip']}",
            f"**Country:** {recipient['country_name']} ({recipient['country_code']})",
            f"",
        ])
    if body.get('costs'):
        costs = body['costs']
        if costs['calculation_status'] == 'done':
            lines.extend([
                "## Costs",
                f"**Currency:** {costs['currency']}",
                f"**Subtotal:** {costs['subtotal']}",
                f"**Shipping:** {costs['shipping']}",
                f"**Tax:** {costs['tax']}",
                f"**Total:** {costs['total']}",
                f"",
            ])
        else:
            lines.extend(["## Costs", f"**Status:** {costs['calculation_status']}", f""])
    if body.get('order_items'):
        lines.append(f"## Order Items ({len(body['order_items'])})")
        for item in body['order_items']:
            lines.extend([
                f"- **Item {item['id']}**: {item.get('name', 'N/A')}",
                f"  - Variant: {item.get('catalog_variant_id', 'N/A')}",
                f"  - Quantity: {item['quantity']}",
                f"  - Price: {item.get('price', 'N/A')} {item.get('currency', '')}",
            ])
        lines.append("")
    return "\n".join(lines)


def orders(data: Dict[str, Any]) -> str:
    """A page of orders."""
    rows = data.get('data', [])
    paging = data.get('paging', {})
    lines = [
        f"# Orders ({paging.get('total', 0)} total)",
        f"",
        f"Showing {len(rows)} orders (offset: {paging.get('offset', 0)}, "
        f"limit: {paging.get('limit', 20)})",
        f"",
    ]
    for row in rows:
        costs = row.get('costs', {})
        lines.extend([
            f"## Order {row['id']}",
            f"- **Status:** {row['status']}",
            f"- **External ID:** {row.get('external_id', 'N/A')}",
            f"- **Total:** {costs.get('total', 'Calculating...')} {costs.get('currency', '')}",
            f"- **Items:** {len(row.get('order_items', []))}",
            f"- **Created:** {row['created_at']}",
            f"",
        ])
    return "\n".join(lines)


def order_items(data: Dict[str, Any], order_id: str) -> str:
    """The items on one order."""
    rows = data.get('data', [])
    lines = [f"# Items on Order {order_id} ({len(rows)})", f""]
    for row in rows:
        lines.extend([
            f"## Item {row.get('id')}",
            f"- **Name:** {row.get('name', 'N/A')}",
            f"- **Variant:** {row.get('catalog_variant_id', 'N/A')}",
            f"- **Quantity:** {row.get('quantity')}",
            f"- **Price:** {row.get('price', 'N/A')} {row.get('currency', '')}",
            f"",
        ])
    return "\n".join(lines)


def shipments(data: Dict[str, Any], order_id: str) -> str:
    """The shipments for one order."""
    rows = data.get('data', [])
    if not rows:
        return (f"# Shipments for Order {order_id}\n\n"
                "No shipments yet. Shipments appear once the order is fulfilled.")
    lines = [f"# Shipments for Order {order_id} ({len(rows)})", f""]
    for row in rows:
        lines.extend([
            f"## Shipment {row.get('id')}",
            f"- **Carrier:** {row.get('carrier', 'N/A')}",
            f"- **Service:** {row.get('service', 'N/A')}",
            f"- **Tracking number:** {row.get('tracking_number', 'N/A')}",
            f"- **Tracking URL:** {row.get('tracking_url', 'N/A')}",
            f"- **Shipped at:** {row.get('shipped_at', 'not yet')}",
            f"",
        ])
    return "\n".join(lines)


def estimate(body: Dict[str, Any], status: str) -> str:
    """One estimation task, in whichever state it is in."""
    if status == "pending":
        return ("# Cost Estimate\n\n**Status:** pending\n\n"
                "The estimate is still being calculated. Call "
                "printful_get_estimation_task again in a few seconds.")
    if status == "failed":
        reasons = body.get("failure_reasons") or []
        detail = "\n".join(f"- {r}" for r in reasons) or "- No reason given."
        return f"# Cost Estimate\n\n**Status:** failed\n\n{detail}"

    costs = (body.get("costs") or {})
    currency = costs.get("currency", "")
    lines = [
        f"# Cost Estimate",
        f"",
        f"**Status:** completed",
        f"**Currency:** {currency}",
        f"**Subtotal:** {costs.get('subtotal', 'N/A')}",
        f"**Shipping:** {costs.get('shipping', 'N/A')}",
        f"**Tax:** {costs.get('tax', 'N/A')}",
        f"**Total:** {costs.get('total', 'N/A')}",
        f"",
    ]
    return "\n".join(lines)


def rates(data: Dict[str, Any]) -> str:
    """Available shipping options."""
    rows = data.get('data', [])
    lines = [f"# Shipping Rates", f"", f"Found {len(rows)} shipping options", f""]
    for row in rows:
        delivery = f"{row['min_delivery_days']}-{row['max_delivery_days']} days"
        lines.extend([
            f"## {row['shipping_method_name']}",
            f"- **Rate:** {row['rate']} {row['currency']}",
            f"- **Delivery:** {delivery} ({row['min_delivery_date']} to "
            f"{row['max_delivery_date']})",
            f"",
        ])
        if row.get('shipments'):
            lines.append("### Shipments")
            for shipment in row['shipments']:
                customs = "Yes" if shipment.get('customs_fees_possible') else "No"
                lines.append(
                    f"- From {shipment['departure_country']} - "
                    f"Customs fees possible: {customs}")
            lines.append("")
    return "\n".join(lines)


def countries(data: Dict[str, Any]) -> str:
    """Every country Printful ships to."""
    rows = data.get('data', [])
    lines = [f"# Available Countries ({len(rows)} total)", f""]
    for row in rows:
        lines.append(f"## {row['name']} ({row['code']})")
        if row.get('states'):
            lines.append(f"**States:** {len(row['states'])} available")
            for state in row['states'][:3]:
                lines.append(f"  - {state['name']} ({state['code']})")
            if len(row['states']) > 3:
                lines.append(f"  - _(and {len(row['states']) - 3} more)_")
        lines.append("")
    return "\n".join(lines)


def tax(data: Dict[str, Any]) -> str:
    """A tax rate for one destination."""
    body = data if not isinstance(data.get('data'), dict) else data['data']
    required = body.get('required')
    lines = [
        f"# Tax Rate",
        f"",
        f"**Tax required:** {'yes' if required else 'no'}",
        f"**Rate:** {body.get('rate', 'N/A')}",
        f"**Shipping taxable:** {'yes' if body.get('shipping_taxable') else 'no'}",
        f"",
    ]
    return "\n".join(lines)


def mockup_task(body: Dict[str, Any]) -> str:
    """One mockup task, in whichever state it is in."""
    lines = [f"# Mockup Task {body['id']}", f"", f"**Status:** {body['status']}", f""]
    if body['status'] == 'completed':
        variant_mockups = body.get('catalog_variant_mockups', [])
        lines.append(f"## Generated Mockups ({len(variant_mockups)} variants)")
        for vm in variant_mockups:
            lines.append(f"### Variant {vm['catalog_variant_id']}")
            for mockup in vm.get('mockups', []):
                lines.extend([
                    f"- **{mockup['display_name']}** ({mockup['placement']})",
                    f"  - Style ID: {mockup['style_id']}",
                    f"  - URL: {mockup['mockup_url']}",
                ])
            lines.append("")
    elif body['status'] == 'pending':
        lines.append("⏳ Mockup generation in progress. Check again in a few seconds.")
    elif body['status'] == 'failed':
        lines.append("❌ Mockup generation failed.")
        if body.get('failure_reasons'):
            lines.append("\n**Reasons:**")
            for reason in body['failure_reasons']:
                lines.append(f"- {reason.get('detail', 'Unknown error')}")
    return "\n".join(lines)


def mockup_styles(data: Dict[str, Any], product_id: int) -> str:
    """The mockup styles available for one product."""
    rows = data.get('data', [])
    lines = [f"# Mockup Styles for Product {product_id} ({len(rows)})", f""]
    for row in rows:
        lines.extend([
            f"## {row.get('name', 'Style')} — ID {row.get('id')}",
            f"- **Placement:** {row.get('placement', 'N/A')}",
            f"- **Technique:** {row.get('technique', 'N/A')}",
            f"",
        ])
    return "\n".join(lines)


def mockup_templates(data: Dict[str, Any], product_id: int) -> str:
    """The print-area templates for one product."""
    rows = data.get('data', [])
    lines = [f"# Mockup Templates for Product {product_id} ({len(rows)})", f""]
    for row in rows:
        lines.extend([
            f"## Template {row.get('id')}",
            f"- **Placement:** {row.get('placement', 'N/A')}",
            f"- **Technique:** {row.get('technique', 'N/A')}",
            f"- **Print area:** {row.get('print_area_width')}x"
            f"{row.get('print_area_height')}",
            f"- **Image:** {row.get('image_url', 'N/A')}",
            f"",
        ])
    return "\n".join(lines)


def file_added(body: Dict[str, Any]) -> str:
    """A file just added to the library, possibly still processing."""
    lines = [
        f"# File Added to Library",
        f"",
        f"**File ID:** {body['id']}",
        f"**Status:** {body['status']}",
        f"**Filename:** {body.get('filename', 'Pending')}",
        f"**Original URL:** {body['url']}",
        f"",
    ]

    if body['status'] == 'ok':
        lines.extend([
            f"**Dimensions:** {body.get('width')}x{body.get('height')}px",
            f"**DPI:** {body.get('dpi')}",
            f"**Size:** {body.get('size')} bytes",
            f"**Preview:** {body.get('preview_url')}",
            f"",
        ])
    elif body['status'] == 'waiting':
        lines.append("⏳ File is being processed. Check status with printful_get_file.")

    return "\n".join(lines)


def file_detail(body: Dict[str, Any]) -> str:
    """One file's full detail, branching on its processing status."""
    lines = [
        f"# File {body['id']}",
        f"",
        f"**Status:** {body['status']}",
        f"**Filename:** {body.get('filename', 'N/A')}",
        f"**MIME Type:** {body.get('mime_type', 'N/A')}",
        f"**Created:** {body['created']}",
        f"",
    ]

    if body['status'] == 'ok':
        lines.extend([
            "## File Details",
            f"- **Dimensions:** {body.get('width')}x{body.get('height')}px",
            f"- **DPI:** {body.get('dpi')}",
            f"- **Size:** {body.get('size')} bytes",
            f"- **Hash:** {body.get('hash')}",
            f"",
            "## URLs",
            f"- **Original:** {body['url']}",
            f"- **Thumbnail:** {body.get('thumbnail_url')}",
            f"- **Preview:** {body.get('preview_url')}",
            f"",
        ])
    elif body['status'] == 'waiting':
        lines.append("⏳ File is still being processed.")
    elif body['status'] == 'failed':
        lines.append("❌ File processing failed. The file may be invalid or inaccessible.")

    return "\n".join(lines)


def stores(data: Dict[str, Any]) -> str:
    """The stores available to the API token."""
    stores = data.get('data', [])

    lines = [
        f"# Stores ({len(stores)} total)",
        f"",
    ]

    for store in stores:
        lines.extend([
            f"## {store['name']}",
            f"- **ID:** {store['id']}",
            f"- **Type:** {store['type']}",
            f"",
        ])

    return "\n".join(lines)


def store_statistics(data: Dict[str, Any], date_from: str, date_to: str) -> str:
    """Store statistics for a date range.

    `date_from`/`date_to` are arguments, not fields in the response body, for
    the same reason `mockup_styles`/`mockup_templates` take `product_id`: the
    identifier printed in the header is the one that was asked for, and the
    body does not carry it back.
    """
    stats = data.get('data', {})
    currency = stats.get('currency', 'USD')

    lines = [
        f"# Store Statistics ({date_from} to {date_to})",
        f"",
        f"**Store ID:** {stats.get('store_id')}",
        f"**Currency:** {currency}",
        f"",
    ]

    # Profit
    if stats.get('profit'):
        profit = stats['profit']
        lines.extend([
            "## Profit",
            f"**Value:** {profit['value']} {currency}",
            f"**Change:** {profit.get('relative_difference', 'N/A')}",
            f"",
        ])

    # Total orders
    if stats.get('total_paid_orders'):
        orders = stats['total_paid_orders']
        lines.extend([
            "## Total Paid Orders",
            f"**Count:** {orders['value']}",
            f"**Change:** {orders.get('relative_difference', 'N/A')}",
            f"",
        ])

    # Printful costs
    if stats.get('printful_costs'):
        costs = stats['printful_costs']
        lines.extend([
            "## Printful Costs",
            f"**Value:** {costs['value']} {currency}",
            f"**Change:** {costs.get('relative_difference', 'N/A')}",
            f"",
        ])

    # Average fulfillment time
    if stats.get('average_fulfillment_time'):
        fulfill = stats['average_fulfillment_time']
        lines.extend([
            "## Average Fulfillment Time",
            f"**Days:** {fulfill['value']}",
            f"**Change:** {fulfill.get('relative_difference', 'N/A')}",
            f"",
        ])

    return "\n".join(lines)


def store_templates(data: Any) -> str:
    """A page of saved product templates.

    v1 only, so this receives the unwrapped `result` rather than a v2
    data/paging envelope. The CLI normalizes the same endpoint at
    printful_cli/core/stores.py and finds two shapes: the documented
    {"items": [...], "paging": {...}} and a bare list. Both render here.
    """
    if isinstance(data, list):
        rows, paging = data, {}
    else:
        rows = data.get('items', [])
        paging = data.get('paging', {})
    lines = [
        f"# Product Templates ({paging.get('total', len(rows))} total)",
        f"",
        f"Showing {len(rows)} templates",
        f"",
    ]
    for row in rows:
        lines.extend([
            f"## {row.get('title', 'Template')} — ID {row.get('id')}",
            f"- **Product ID:** {row.get('product_id', 'N/A')}",
            f"- **Created:** {row.get('created_at', 'N/A')}",
            f"",
        ])
    return "\n".join(lines)


def sync_products(data: Dict[str, Any]) -> str:
    """A page of v1 sync products. `data` is the v1 result, already unwrapped."""
    products = data if isinstance(data, list) else []

    lines = [
        f"# Sync Products ({len(products)} shown)",
        f"",
        f"**Note:** Using v1 API (sync products not yet in v2)",
        f"",
    ]

    for product in products:
        lines.extend([
            f"## {product.get('name', 'Unnamed')}",
            f"- **Sync Product ID:** {product['id']}",
            f"- **Sync Variants:** {len(product.get('sync_variants', []))}",
            f"- **External ID:** {product.get('external_id', 'N/A')}",
            f"",
        ])

    return "\n".join(lines)


def sync_product(body: Dict[str, Any]) -> str:
    """One v1 sync product with its variants."""
    product = body.get('sync_product', {})
    variants = body.get('sync_variants', [])

    lines = [
        f"# {product.get('name', 'Sync Product')}",
        f"",
        f"**Sync Product ID:** {product['id']}",
        f"**External ID:** {product.get('external_id', 'N/A')}",
        f"**Thumbnail:** {product.get('thumbnail_url', 'N/A')}",
        f"",
        f"**Note:** Using v1 API (sync products not yet in v2)",
        f"",
    ]

    if variants:
        lines.append(f"## Sync Variants ({len(variants)})")
        for variant in variants:
            lines.extend([
                f"### Variant {variant['id']}",
                f"- **Name:** {variant.get('name', 'N/A')}",
                f"- **External ID:** {variant.get('external_id', 'N/A')}",
                f"- **Variant ID:** {variant.get('variant_id', 'N/A')}",
                f"- **Retail Price:** {variant.get('retail_price', 'N/A')} {variant.get('currency', '')}",
                f"",
            ])

    return "\n".join(lines)

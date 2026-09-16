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
        f"# {body.get('name', 'Unnamed')}",
        f"",
        f"**ID:** {body.get('id', 'unknown')}",
        f"**Type:** {body.get('type', 'N/A')}",
        f"**Brand:** {body.get('brand', 'N/A')}",
        f"**Variants:** {body.get('variant_count', 'N/A')}",
        f"**Status:** {'Discontinued' if body.get('is_discontinued') else 'Available'}",
        f"",
    ]
    if body.get('description'):
        lines.extend(["## Description", body['description'], ""])
    if body.get('techniques'):
        lines.append("## Available Techniques")
        for tech in body['techniques']:
            default = " (default)" if tech.get('is_default') else ""
            lines.append(
                f"- **{tech.get('display_name', 'N/A')}** "
                f"({tech.get('key', 'N/A')}){default}")
        lines.append("")
    if body.get('placements'):
        lines.append(f"## Placements ({len(body['placements'])} available)")
        for placement in body['placements'][:5]:
            lines.append(f"- {placement.get('placement', 'N/A')} - "
                         f"{placement.get('technique', 'N/A')}")
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
            f"## {row.get('name', 'Unnamed')}",
            f"- **ID:** {row.get('id', 'unknown')}",
            f"- **Type:** {row.get('type', 'N/A')}",
            f"- **Variants:** {row.get('variant_count', 'N/A')}",
            f"- **Techniques:** "
            f"{', '.join(t.get('key', 'N/A') for t in row.get('techniques', []))}",
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
            f"## {row.get('name', 'Unnamed')}",
            f"- **Variant ID:** {row.get('id', 'unknown')}",
            f"- **Size:** {row.get('size', 'N/A')}",
            f"- **Color:** {row.get('color', 'N/A')} ({row.get('color_code', 'N/A')})",
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
                f"- **{tech.get('technique_display_name', 'N/A')}:** "
                f"{tech.get('price', 'N/A')} {currency}")
        lines.append("")
    if body.get('product', {}).get('placements'):
        lines.append("## Additional Placement Prices")
        for placement in body['product']['placements']:
            lines.append(
                f"- **{placement.get('title', 'N/A')}:** "
                f"{placement.get('price', 'N/A')} {currency}")
        lines.append("")
    return "\n".join(lines)


def availability(data: Dict[str, Any], product_id: int) -> str:
    """Stock availability per variant and technique."""
    lines = [f"# Availability for Product {product_id}", f""]
    for row in data.get('data', []):
        lines.append(f"## Variant {row.get('catalog_variant_id', 'unknown')}")
        for tech in row.get('techniques', []):
            lines.append(f"### {tech.get('technique', 'N/A')}")
            for region in tech.get('selling_regions', []):
                lines.append(f"- **{region.get('name', 'N/A')}:** "
                             f"{region.get('availability', 'N/A')}")
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
        lines.append(
            f"- **{row.get('title', 'Category')}** — ID {row.get('id', 'unknown')}{suffix}")
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
        f"# Order {body.get('id', 'unknown')}",
        f"",
        f"**Status:** {body.get('status', 'unknown')}",
        f"**External ID:** {body.get('external_id', 'N/A')}",
        f"**Created:** {body.get('created_at', 'N/A')}",
        f"**Updated:** {body.get('updated_at', 'N/A')}",
        f"",
    ]
    if body.get('recipient'):
        recipient = body['recipient']
        lines.extend([
            "## Recipient",
            f"**Name:** {recipient.get('name', 'N/A')}",
            f"**Address:** {recipient.get('address1', 'N/A')}",
            f"**City:** {recipient.get('city', 'N/A')}, "
            f"{recipient.get('state_code', '')} {recipient.get('zip', 'N/A')}",
            f"**Country:** {recipient.get('country_name', 'N/A')} "
            f"({recipient.get('country_code', 'N/A')})",
            f"",
        ])
    if body.get('costs'):
        costs = body['costs']
        if costs.get('calculation_status') == 'done':
            lines.extend([
                "## Costs",
                f"**Currency:** {costs.get('currency', '')}",
                f"**Subtotal:** {costs.get('subtotal', 'N/A')}",
                f"**Shipping:** {costs.get('shipping', 'N/A')}",
                f"**Tax:** {costs.get('tax', 'N/A')}",
                f"**Total:** {costs.get('total', 'N/A')}",
                f"",
            ])
        else:
            lines.extend(["## Costs",
                          f"**Status:** {costs.get('calculation_status', 'unknown')}",
                          f""])
    if body.get('order_items'):
        lines.append(f"## Order Items ({len(body['order_items'])})")
        for item in body['order_items']:
            lines.extend([
                f"- **Item {item.get('id', 'unknown')}**: {item.get('name', 'N/A')}",
                f"  - Variant: {item.get('catalog_variant_id', 'N/A')}",
                f"  - Quantity: {item.get('quantity', 'N/A')}",
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
            f"## Order {row.get('id', 'unknown')}",
            f"- **Status:** {row.get('status', 'unknown')}",
            f"- **External ID:** {row.get('external_id', 'N/A')}",
            f"- **Total:** {costs.get('total', 'Calculating...')} {costs.get('currency', '')}",
            f"- **Items:** {len(row.get('order_items', []))}",
            f"- **Created:** {row.get('created_at', 'N/A')}",
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
        delivery = (f"{row.get('min_delivery_days', 'N/A')}-"
                    f"{row.get('max_delivery_days', 'N/A')} days")
        lines.extend([
            f"## {row.get('shipping_method_name', 'Shipping option')}",
            f"- **Rate:** {row.get('rate', 'N/A')} {row.get('currency', '')}",
            f"- **Delivery:** {delivery} ({row.get('min_delivery_date', 'N/A')} to "
            f"{row.get('max_delivery_date', 'N/A')})",
            f"",
        ])
        if row.get('shipments'):
            lines.append("### Shipments")
            for shipment in row['shipments']:
                customs = "Yes" if shipment.get('customs_fees_possible') else "No"
                lines.append(
                    f"- From {shipment.get('departure_country', 'N/A')} - "
                    f"Customs fees possible: {customs}")
            lines.append("")
    return "\n".join(lines)


def countries(data: Dict[str, Any]) -> str:
    """Every country Printful ships to."""
    rows = data.get('data', [])
    lines = [f"# Available Countries ({len(rows)} total)", f""]
    for row in rows:
        lines.append(f"## {row.get('name', 'Unnamed')} ({row.get('code', 'N/A')})")
        if row.get('states'):
            lines.append(f"**States:** {len(row['states'])} available")
            for state in row['states'][:3]:
                lines.append(
                    f"  - {state.get('name', 'N/A')} ({state.get('code', 'N/A')})")
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
    lines = [f"# Mockup Task {body.get('id', 'unknown')}", f"",
             f"**Status:** {body.get('status', 'unknown')}", f""]
    if body.get('status') == 'completed':
        variant_mockups = body.get('catalog_variant_mockups', [])
        lines.append(f"## Generated Mockups ({len(variant_mockups)} variants)")
        for vm in variant_mockups:
            lines.append(f"### Variant {vm.get('catalog_variant_id', 'unknown')}")
            for mockup in vm.get('mockups', []):
                lines.extend([
                    f"- **{mockup.get('display_name', 'N/A')}** "
                    f"({mockup.get('placement', 'N/A')})",
                    f"  - Style ID: {mockup.get('style_id', 'N/A')}",
                    f"  - URL: {mockup.get('mockup_url', 'N/A')}",
                ])
            lines.append("")
    elif body.get('status') == 'pending':
        lines.append("⏳ Mockup generation in progress. Check again in a few seconds.")
    elif body.get('status') == 'failed':
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
        f"**File ID:** {body.get('id', 'unknown')}",
        f"**Status:** {body.get('status', 'unknown')}",
        f"**Filename:** {body.get('filename', 'Pending')}",
        f"**Original URL:** {body.get('url', 'N/A')}",
        f"",
    ]

    if body.get('status') == 'ok':
        lines.extend([
            f"**Dimensions:** {body.get('width')}x{body.get('height')}px",
            f"**DPI:** {body.get('dpi')}",
            f"**Size:** {body.get('size')} bytes",
            f"**Preview:** {body.get('preview_url')}",
            f"",
        ])
    elif body.get('status') == 'waiting':
        lines.append("⏳ File is being processed. Check status with printful_get_file.")

    return "\n".join(lines)


def file_detail(body: Dict[str, Any]) -> str:
    """One file's full detail, branching on its processing status."""
    lines = [
        f"# File {body.get('id', 'unknown')}",
        f"",
        f"**Status:** {body.get('status', 'unknown')}",
        f"**Filename:** {body.get('filename', 'N/A')}",
        f"**MIME Type:** {body.get('mime_type', 'N/A')}",
        f"**Created:** {body.get('created', 'N/A')}",
        f"",
    ]

    if body.get('status') == 'ok':
        lines.extend([
            "## File Details",
            f"- **Dimensions:** {body.get('width')}x{body.get('height')}px",
            f"- **DPI:** {body.get('dpi')}",
            f"- **Size:** {body.get('size')} bytes",
            f"- **Hash:** {body.get('hash')}",
            f"",
            "## URLs",
            f"- **Original:** {body.get('url', 'N/A')}",
            f"- **Thumbnail:** {body.get('thumbnail_url')}",
            f"- **Preview:** {body.get('preview_url')}",
            f"",
        ])
    elif body.get('status') == 'waiting':
        lines.append("⏳ File is still being processed.")
    elif body.get('status') == 'failed':
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
            f"## {store.get('name', 'Unnamed')}",
            f"- **ID:** {store.get('id', 'unknown')}",
            f"- **Type:** {store.get('type', 'N/A')}",
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
            f"**Value:** {profit.get('value', 'N/A')} {currency}",
            f"**Change:** {profit.get('relative_difference', 'N/A')}",
            f"",
        ])

    # Total orders
    if stats.get('total_paid_orders'):
        orders = stats['total_paid_orders']
        lines.extend([
            "## Total Paid Orders",
            f"**Count:** {orders.get('value', 'N/A')}",
            f"**Change:** {orders.get('relative_difference', 'N/A')}",
            f"",
        ])

    # Printful costs
    if stats.get('printful_costs'):
        costs = stats['printful_costs']
        lines.extend([
            "## Printful Costs",
            f"**Value:** {costs.get('value', 'N/A')} {currency}",
            f"**Change:** {costs.get('relative_difference', 'N/A')}",
            f"",
        ])

    # Average fulfillment time
    if stats.get('average_fulfillment_time'):
        fulfill = stats['average_fulfillment_time']
        lines.extend([
            "## Average Fulfillment Time",
            f"**Days:** {fulfill.get('value', 'N/A')}",
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


def sync_products(data: Any) -> str:
    """A page of v1 sync products. `data` is the v1 result, already unwrapped.

    v1 only, so the same two shapes `store_templates` documents can arrive here:
    a bare list, and the documented {"items": [...], "paging": {...}} envelope.
    Reading only the list rendered the envelope as "0 shown" — a wrong answer
    with no error, which is the v1 trap `CLAUDE.md` warns about.
    """
    products = data if isinstance(data, list) else data.get('items', [])

    lines = [
        f"# Sync Products ({len(products)} shown)",
        f"",
        f"**Note:** Using v1 API (sync products not yet in v2)",
        f"",
    ]

    for product in products:
        lines.extend([
            f"## {product.get('name', 'Unnamed')}",
            f"- **Sync Product ID:** {product.get('id', 'unknown')}",
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
        f"**Sync Product ID:** {product.get('id', 'unknown')}",
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
                f"### Variant {variant.get('id', 'unknown')}",
                f"- **Name:** {variant.get('name', 'N/A')}",
                f"- **External ID:** {variant.get('external_id', 'N/A')}",
                f"- **Variant ID:** {variant.get('variant_id', 'N/A')}",
                f"- **Retail Price:** {variant.get('retail_price', 'N/A')} {variant.get('currency', '')}",
                f"",
            ])

    return "\n".join(lines)

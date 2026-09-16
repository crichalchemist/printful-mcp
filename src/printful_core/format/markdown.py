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

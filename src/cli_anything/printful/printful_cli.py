"""cli-anything-printful — command-line harness for the Printful API.

Safety: `orders confirm` submits an order for fulfillment and charges the account.
`orders cancel` is destructive. Both refuse to run without an explicit --yes.
"""
from __future__ import annotations

import functools
import json as json_mod
import os
import sys
from typing import Any, Dict, List, Optional

import click

from . import __version__
from .core import catalog as catalog_mod
from .core import files as files_mod
from .core import mockups as mockups_mod
from .core import orders as orders_mod
from .core import session as session_mod
from .core import shipping as shipping_mod
from .core import stores as stores_mod
from .core import sync as sync_mod
from .utils.printful_backend import (
    PrintfulAuthError,
    PrintfulBackend,
    PrintfulError,
    PrintfulRateLimitError,
    load_config,
    save_config,
    CONFIG_FILE,
)
from .utils.repl_skin import ReplSkin

_repl_mode = False
_session: Optional[session_mod.PrintfulSession] = None
_backend: Optional[PrintfulBackend] = None
_skin: Optional[ReplSkin] = None


# --------------------------------------------------------------------------
# Shared helpers
# --------------------------------------------------------------------------

def get_skin() -> ReplSkin:
    global _skin
    if _skin is None:
        _skin = ReplSkin("printful", version=__version__)
    return _skin


def get_session(session_file: Optional[str] = None) -> session_mod.PrintfulSession:
    global _session
    if _session is None:
        _session = session_mod.PrintfulSession(session_file)
    return _session


def get_backend(ctx) -> PrintfulBackend:
    """Build the API client lazily so --help and config commands need no token."""
    global _backend
    if _backend is None:
        _backend = PrintfulBackend(
            api_key=ctx.obj.get("api_key"),
            store_id=ctx.obj.get("store_id") or get_session().store_id,
        )
    return _backend


def output(ctx, data: Any, message: str = "", table: Optional[Dict[str, Any]] = None) -> None:
    """Emit a result as JSON or human-readable text."""
    if ctx.obj.get("json"):
        click.echo(json_mod.dumps(data, indent=2, default=str))
        return

    skin = get_skin()
    if table and table.get("rows"):
        skin.table(table["headers"], table["rows"])
    elif isinstance(data, dict):
        _print_dict(data)
    elif isinstance(data, list):
        for item in data:
            click.echo(f"  {item}")
    else:
        click.echo(str(data))
    if message:
        skin.success(message)


def _print_dict(d: Dict[str, Any], indent: int = 0) -> None:
    pad = "  " * (indent + 1)
    for key, value in d.items():
        if isinstance(value, dict):
            click.echo(f"{pad}{key}:")
            _print_dict(value, indent + 1)
        elif isinstance(value, list):
            if not value:
                click.echo(f"{pad}{key}: (none)")
            else:
                click.echo(f"{pad}{key}: ({len(value)} item(s))")
                for item in value[:10]:
                    if isinstance(item, dict):
                        preview = ", ".join(
                            f"{k}={v}" for k, v in list(item.items())[:4]
                        )
                        click.echo(f"{pad}  - {preview}")
                    else:
                        click.echo(f"{pad}  - {item}")
                if len(value) > 10:
                    click.echo(f"{pad}  ... and {len(value) - 10} more")
        else:
            click.echo(f"{pad}{key}: {value}")


def handle_error(func):
    """Fail loudly with an actionable message; agents need this to self-correct."""

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except PrintfulRateLimitError as e:
            _fail(e.message, {"error": e.message, "retry_after": e.retry_after,
                              "status_code": e.status_code})
        except PrintfulAuthError as e:
            _fail(e.message, e.to_dict())
        except PrintfulError as e:
            payload = e.to_dict()
            message = e.message
            # Account-level tokens hit this on every store-scoped endpoint.
            # Say what to do about it instead of just relaying the API's text.
            if "store_id" in message.lower():
                hint = (
                    "This token is account-level, so a store must be selected "
                    "first:\n  cli-anything-printful store use          "
                    "# pick from a list\n  cli-anything-printful store use <ID> "
                    "--save   # set the default"
                )
                message = f"{message}\n{hint}"
                payload["hint"] = hint
            _fail(message, payload)
        except (ValueError, KeyError) as e:
            _fail(str(e), {"error": str(e)})

    return wrapper


def _fail(message: str, payload: Dict[str, Any]) -> None:
    ctx = click.get_current_context(silent=True)
    use_json = bool(ctx and ctx.obj and ctx.obj.get("json"))
    if use_json:
        click.echo(json_mod.dumps(payload, indent=2, default=str), err=True)
    else:
        get_skin().error(message)
    if _repl_mode:
        return
    sys.exit(1)


def _parse_ids(value: Optional[str]) -> List[int]:
    """Parse a comma-separated ID list into ints, failing loudly on junk."""
    if not value:
        return []
    out = []
    for chunk in str(value).split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        try:
            out.append(int(chunk))
        except ValueError:
            raise ValueError(f"Invalid ID '{chunk}' — expected a comma-separated list of integers.")
    return out


def _load_items_json(items_json: Optional[str]) -> List[Dict[str, Any]]:
    """Parse an --items JSON array, or fall back to the session draft's items."""
    if items_json:
        try:
            items = json_mod.loads(items_json)
        except json_mod.JSONDecodeError as e:
            raise ValueError(f"--items is not valid JSON: {e}")
        if not isinstance(items, list):
            raise ValueError("--items must be a JSON array of order items.")
        return items
    items = get_session().draft.items
    if not items:
        raise ValueError(
            "No items given. Pass --items '[{\"catalog_variant_id\":123,"
            "\"quantity\":1}]' or build a draft with: draft add-item"
        )
    return items


def _require_yes(yes: bool, action: str, detail: str) -> None:
    """Gate billable and destructive operations behind an explicit flag."""
    if yes:
        return
    raise ValueError(
        f"Refusing to {action} without --yes.\n{detail}\n"
        f"Re-run with --yes once you are sure."
    )


# --------------------------------------------------------------------------
# Main group
# --------------------------------------------------------------------------

@click.group(invoke_without_command=True)
@click.option("--json", "use_json", is_flag=True, help="Output as JSON")
@click.option("--dry-run", "dry_run", is_flag=True, default=False,
              help="Run without saving session changes to disk")
@click.option("--api-key", "api_key", default=None,
              help="Printful API token (overrides env and config)")
@click.option("--store-id", "store_id", default=None,
              help="Store ID for account-level tokens (sets X-PF-Store-Id)")
@click.option("--session", "session_file", default=None,
              help="Path to the session file")
@click.version_option(version=__version__, prog_name="cli-anything-printful")
@click.pass_context
def cli(ctx, use_json, dry_run, api_key, store_id, session_file):
    """Command-line harness for the Printful print-on-demand API.

    Runs the interactive REPL when called with no subcommand.
    """
    ctx.ensure_object(dict)
    ctx.obj["json"] = use_json
    ctx.obj["dry_run"] = dry_run
    ctx.obj["api_key"] = api_key
    ctx.obj["store_id"] = store_id
    ctx.obj["session_file"] = session_file
    get_session(session_file)
    if ctx.invoked_subcommand is None:
        ctx.invoke(repl)


@cli.result_callback()
@click.pass_context
def auto_save_on_exit(ctx, result, use_json, dry_run, api_key, store_id, session_file):
    """Persist session changes after one-shot mutations."""
    if _repl_mode or dry_run:
        return
    sess = get_session()
    if sess._modified:
        try:
            sess.save_session()
        except Exception as e:  # pragma: no cover - disk failure path
            click.echo(f"Warning: Auto-save failed: {e}", err=True)


# --------------------------------------------------------------------------
# catalog
# --------------------------------------------------------------------------

@cli.group()
def catalog():
    """Browse the Printful product catalog (v2)."""


@catalog.command("products")
@click.option("--limit", default=20, show_default=True)
@click.option("--offset", default=0, show_default=True)
@click.option("--category-ids", default=None, help="Comma-separated category IDs")
@click.option("--colors", default=None, help="Comma-separated color names")
@click.option("--techniques", default=None, help="Comma-separated techniques (dtg, embroidery)")
@click.option("--types", default=None, help="Comma-separated product types")
@click.pass_context
@handle_error
def catalog_products(ctx, limit, offset, category_ids, colors, techniques, types):
    """List catalog products."""
    data = catalog_mod.list_products(
        get_backend(ctx), limit, offset, category_ids, colors, techniques, types
    )
    summary = catalog_mod.summarize_products(data)
    output(
        ctx,
        summary,
        table={
            "headers": ["ID", "Name", "Type", "Variants"],
            "rows": [
                [str(p["id"]), str(p["name"]), str(p["type"]), str(p["variants"])]
                for p in summary["products"]
            ],
        },
    )


@catalog.command("product")
@click.argument("product_id", type=int)
@click.pass_context
@handle_error
def catalog_product(ctx, product_id):
    """Get details for one catalog product."""
    data = catalog_mod.get_product(get_backend(ctx), product_id)
    output(ctx, data.get("data", data))


@catalog.command("variants")
@click.argument("product_id", type=int)
@click.option("--limit", default=20, show_default=True)
@click.option("--offset", default=0, show_default=True)
@click.pass_context
@handle_error
def catalog_variants(ctx, product_id, limit, offset):
    """List variants (size/color combinations) for a product."""
    data = catalog_mod.list_variants(get_backend(ctx), product_id, limit, offset)
    summary = catalog_mod.summarize_variants(data)
    output(
        ctx,
        summary,
        table={
            "headers": ["ID", "Name", "Size", "Color"],
            "rows": [
                [str(v["id"]), str(v["name"]), str(v["size"]), str(v["color"])]
                for v in summary["variants"]
            ],
        },
    )


@catalog.command("variant-price")
@click.argument("variant_id", type=int)
@click.option("--currency", default=None, help="Currency code (e.g. USD)")
@click.pass_context
@handle_error
def catalog_variant_price(ctx, variant_id, currency):
    """Get pricing for a catalog variant."""
    data = catalog_mod.get_variant_prices(get_backend(ctx), variant_id, currency)
    output(ctx, data.get("data", data))


@catalog.command("availability")
@click.argument("product_id", type=int)
@click.option("--techniques", default=None)
@click.pass_context
@handle_error
def catalog_availability(ctx, product_id, techniques):
    """Get stock availability for a product."""
    data = catalog_mod.get_availability(get_backend(ctx), product_id, techniques)
    output(ctx, data.get("data", data))


@catalog.command("categories")
@click.option("--limit", default=20, show_default=True)
@click.option("--offset", default=0, show_default=True)
@click.pass_context
@handle_error
def catalog_categories(ctx, limit, offset):
    """List catalog categories."""
    data = catalog_mod.list_categories(get_backend(ctx), limit, offset)
    rows = data.get("data", []) or []
    output(
        ctx,
        {"categories": rows, "count": len(rows)},
        table={
            "headers": ["ID", "Title", "Parent"],
            "rows": [
                [str(c.get("id")), str(c.get("title")), str(c.get("parent_id"))]
                for c in rows
            ],
        },
    )


@catalog.command("category")
@click.argument("category_id", type=int)
@click.pass_context
@handle_error
def catalog_category(ctx, category_id):
    """Get one catalog category."""
    data = catalog_mod.get_category(get_backend(ctx), category_id)
    output(ctx, data.get("data", data))


@catalog.command("size-guide")
@click.argument("product_id", type=int)
@click.option("--unit", default=None, type=click.Choice(["inches", "cm"]))
@click.pass_context
@handle_error
def catalog_size_guide(ctx, product_id, unit):
    """Get the size guide for a product."""
    data = catalog_mod.get_size_guide(get_backend(ctx), product_id, unit)
    output(ctx, data.get("data", data))


# --------------------------------------------------------------------------
# orders
# --------------------------------------------------------------------------

@cli.group()
def orders():
    """Manage orders. `confirm` and `cancel` require --yes."""


@orders.command("list")
@click.option("--limit", default=20, show_default=True)
@click.option("--offset", default=0, show_default=True)
@click.option("--status", default=None, help="Filter by order status")
@click.pass_context
@handle_error
def orders_list(ctx, limit, offset, status):
    """List orders."""
    data = orders_mod.list_orders(get_backend(ctx), limit, offset, status)
    summary = orders_mod.summarize_orders(data)
    output(
        ctx,
        summary,
        table={
            "headers": ["ID", "Status", "Created", "Total"],
            "rows": [
                [str(o["id"]), str(o["status"]), str(o["created"]),
                 f"{o['total']} {o['currency'] or ''}".strip()]
                for o in summary["orders"]
            ],
        },
    )


@orders.command("get")
@click.argument("order_id")
@click.pass_context
@handle_error
def orders_get(ctx, order_id):
    """Get one order. Prefix an external ID with @."""
    data = orders_mod.get_order(get_backend(ctx), order_id)
    output(ctx, data.get("data", data))


@orders.command("create")
@click.option("--items", "items_json", default=None,
              help="JSON array of order items (defaults to the session draft)")
@click.option("--name", default=None)
@click.option("--address1", default=None)
@click.option("--city", default=None)
@click.option("--state-code", default=None)
@click.option("--country-code", default=None)
@click.option("--zip", "zip_code", default=None)
@click.option("--email", default=None)
@click.option("--external-id", default=None)
@click.pass_context
@handle_error
def orders_create(ctx, items_json, name, address1, city, state_code, country_code,
                  zip_code, email, external_id):
    """Create a DRAFT order. Drafts are not charged until confirmed."""
    sess = get_session()
    recipient_flags = {
        "name": name, "address1": address1, "city": city,
        "state_code": state_code, "country_code": country_code,
        "zip": zip_code, "email": email,
    }
    if any(v for v in recipient_flags.values()):
        sess.draft.set_recipient(**recipient_flags)
        sess.touch()
    if items_json:
        payload = {
            "recipient": sess.draft.recipient,
            "order_items": _load_items_json(items_json),
        }
        if external_id:
            payload["external_id"] = external_id
        missing = sess.draft.missing_fields()
        missing = [m for m in missing if not m.startswith("items")]
        if missing:
            raise ValueError("Recipient incomplete. Missing: " + ", ".join(missing))
    else:
        if external_id:
            sess.draft.external_id = external_id
        payload = sess.draft.to_api_payload()

    if ctx.obj.get("dry_run"):
        output(ctx, {"dry_run": True, "would_post": "/v2/orders", "payload": payload},
               message="Dry run — no order created.")
        return

    data = orders_mod.create_order(get_backend(ctx), payload)
    body = data.get("data", data)
    sess.save_history(f"orders create -> {body.get('id')}", {"id": body.get("id")})
    output(ctx, body,
           message=f"Draft order {body.get('id')} created (not charged until confirmed).")


@orders.command("update")
@click.argument("order_id")
@click.option("--shipping", default=None, help="Shipping method code")
@click.option("--external-id", default=None)
@click.pass_context
@handle_error
def orders_update(ctx, order_id, shipping, external_id):
    """Update a draft order (PATCH)."""
    payload = {k: v for k, v in
               {"shipping": shipping, "external_id": external_id}.items() if v}
    if not payload:
        raise ValueError("Nothing to update. Pass --shipping and/or --external-id.")
    if ctx.obj.get("dry_run"):
        output(ctx, {"dry_run": True, "would_patch": f"/v2/orders/{order_id}",
                     "payload": payload}, message="Dry run — no change made.")
        return
    data = orders_mod.update_order(get_backend(ctx), order_id, payload)
    output(ctx, data.get("data", data), message=f"Order {order_id} updated.")


@orders.command("cancel")
@click.argument("order_id")
@click.option("--yes", is_flag=True, default=False,
              help="Required. Confirms this destructive action.")
@click.pass_context
@handle_error
def orders_cancel(ctx, order_id, yes):
    """Cancel an order. DESTRUCTIVE — requires --yes."""
    _require_yes(yes, f"cancel order {order_id}",
                 "Cancelling an order cannot be undone.")
    if ctx.obj.get("dry_run"):
        output(ctx, {"dry_run": True, "would_delete": f"/v2/orders/{order_id}"},
               message="Dry run — nothing cancelled.")
        return
    data = orders_mod.cancel_order(get_backend(ctx), order_id)
    get_session().save_history(f"orders cancel {order_id}", {"order_id": order_id})
    output(ctx, data, message=f"Order {order_id} cancelled.")


@orders.command("confirm")
@click.argument("order_id")
@click.option("--yes", is_flag=True, default=False,
              help="Required. Confirms that this CHARGES your account.")
@click.pass_context
@handle_error
def orders_confirm(ctx, order_id, yes):
    """Confirm an order for fulfillment. CHARGES YOUR ACCOUNT — requires --yes."""
    _require_yes(
        yes, f"confirm order {order_id}",
        "Confirming submits the order to production and CHARGES your Printful account. "
        "This is real money and cannot be undone once fulfillment starts.",
    )
    if ctx.obj.get("dry_run"):
        output(ctx, {"dry_run": True,
                     "would_post": f"/v2/orders/{order_id}/confirmation"},
               message="Dry run — order NOT confirmed, nothing charged.")
        return
    data = orders_mod.confirm_order(get_backend(ctx), order_id)
    get_session().save_history(f"orders confirm {order_id}", {"order_id": order_id})
    output(ctx, data.get("data", data),
           message=f"Order {order_id} confirmed and submitted for fulfillment.")


@orders.command("estimate")
@click.option("--items", "items_json", default=None,
              help="JSON array of order items (defaults to the session draft)")
@click.option("--no-poll", is_flag=True, default=False,
              help="Return the task ID without waiting for the result")
@click.option("--max-wait", default=30.0, show_default=True)
@click.pass_context
@handle_error
def orders_estimate(ctx, items_json, no_poll, max_wait):
    """Estimate order costs without placing an order. Free."""
    sess = get_session()
    items = _load_items_json(items_json)
    recipient = sess.draft.recipient
    if not recipient.get("country_code"):
        raise ValueError(
            "Estimation needs a recipient country. Set one with: "
            "draft recipient --country-code US --state-code CA ..."
        )
    payload = {"recipient": recipient, "order_items": items}
    if ctx.obj.get("dry_run"):
        output(ctx, {"dry_run": True, "would_post": "/v2/order-estimation-tasks",
                     "payload": payload}, message="Dry run — no estimate requested.")
        return
    data = orders_mod.estimate_costs(
        get_backend(ctx), payload, poll=not no_poll, max_wait=max_wait
    )
    output(ctx, data.get("data", data))


@orders.command("items")
@click.argument("order_id")
@click.pass_context
@handle_error
def orders_items(ctx, order_id):
    """List the items on an order."""
    data = orders_mod.list_order_items(get_backend(ctx), order_id)
    output(ctx, data.get("data", data))


@orders.command("shipments")
@click.argument("order_id")
@click.pass_context
@handle_error
def orders_shipments(ctx, order_id):
    """List shipments for an order."""
    data = orders_mod.list_shipments(get_backend(ctx), order_id)
    output(ctx, data.get("data", data))


# --------------------------------------------------------------------------
# ship
# --------------------------------------------------------------------------

@cli.group()
def ship():
    """Shipping rates, countries, and tax."""


@ship.command("rates")
@click.option("--items", "items_json", default=None,
              help="JSON array of order items (defaults to the session draft)")
@click.option("--country-code", default=None)
@click.option("--state-code", default=None)
@click.option("--city", default=None)
@click.option("--zip", "zip_code", default=None)
@click.option("--currency", default=None)
@click.pass_context
@handle_error
def ship_rates(ctx, items_json, country_code, state_code, city, zip_code, currency):
    """Calculate live shipping rates."""
    sess = get_session()
    recipient = dict(sess.draft.recipient)
    for key, value in {
        "country_code": country_code, "state_code": state_code,
        "city": city, "zip": zip_code,
    }.items():
        if value:
            recipient[key] = value
    if not recipient.get("country_code"):
        raise ValueError("A recipient country is required (--country-code).")
    items = _load_items_json(items_json)
    data = shipping_mod.calculate_rates(get_backend(ctx), recipient, items, currency)
    summary = shipping_mod.summarize_rates(data)
    output(
        ctx,
        summary,
        table={
            "headers": ["ID", "Name", "Rate", "Days"],
            "rows": [
                [str(r["id"]), str(r["name"]),
                 f"{r['rate']} {r['currency'] or ''}".strip(),
                 f"{r['min_days']}-{r['max_days']}"]
                for r in summary["rates"]
            ],
        },
    )


@ship.command("countries")
@click.pass_context
@handle_error
def ship_countries(ctx):
    """List countries Printful ships to."""
    data = shipping_mod.list_countries(get_backend(ctx))
    summary = shipping_mod.summarize_countries(data)
    if ctx.obj.get("json"):
        output(ctx, summary)
        return
    output(ctx, summary, table={
        "headers": ["Code", "Name", "States"],
        "rows": [[str(c["code"]), str(c["name"]), str(c["states"])]
                 for c in summary["countries"][:50]],
    })


@ship.command("tax")
@click.option("--country-code", required=True)
@click.option("--state-code", default=None)
@click.option("--city", default=None)
@click.option("--zip", "zip_code", default=None)
@click.pass_context
@handle_error
def ship_tax(ctx, country_code, state_code, city, zip_code):
    """Calculate a tax rate (v1 — no v2 equivalent exists)."""
    data = shipping_mod.calculate_tax(
        get_backend(ctx), country_code, state_code, city, zip_code
    )
    output(ctx, data)


# --------------------------------------------------------------------------
# mockup
# --------------------------------------------------------------------------

@cli.group()
def mockup():
    """Generate and inspect product mockups. Tightly rate limited."""


@mockup.command("create")
@click.option("--product-id", type=int, required=True)
@click.option("--variant-ids", required=True, help="Comma-separated variant IDs")
@click.option("--image-url", required=True, help="URL of the design image")
@click.option("--placement", default="front", show_default=True)
@click.option("--technique", default="dtg", show_default=True)
@click.option("--style-ids", default=None, help="Comma-separated mockup style IDs")
@click.option("--format", "image_format", default="jpg",
              type=click.Choice(["jpg", "png"]), show_default=True)
@click.option("--wait", is_flag=True, default=False, help="Poll until the task finishes")
@click.pass_context
@handle_error
def mockup_create(ctx, product_id, variant_ids, image_url, placement, technique,
                  style_ids, image_format, wait):
    """Create a mockup generation task."""
    variants = _parse_ids(variant_ids)
    styles = _parse_ids(style_ids)
    if ctx.obj.get("dry_run"):
        output(ctx, {"dry_run": True, "would_post": "/v2/mockup-tasks",
                     "product_id": product_id, "variant_ids": variants},
               message="Dry run — no mockup task created.")
        return
    backend = get_backend(ctx)
    data = mockups_mod.create_task(
        backend, product_id, variants, image_url, placement, technique,
        styles or None, image_format,
    )
    body = data.get("data", data)
    task_id = body.get("id") if isinstance(body, dict) else None
    if wait and task_id:
        data = mockups_mod.wait_for_task(backend, task_id)
        body = data.get("data", data)
    urls = mockups_mod.extract_mockup_urls(data)
    result = {"task": body, "mockup_urls": urls}
    get_session().save_history(f"mockup create -> {task_id}", {"task_id": task_id})
    output(ctx, result, message=mockups_mod.RATE_LIMIT_NOTE if not wait else "")


@mockup.command("status")
@click.argument("task_id")
@click.option("--wait", is_flag=True, default=False)
@click.pass_context
@handle_error
def mockup_status(ctx, task_id, wait):
    """Check a mockup generation task."""
    backend = get_backend(ctx)
    data = (mockups_mod.wait_for_task(backend, task_id) if wait
            else mockups_mod.get_task(backend, task_id))
    output(ctx, {"task": data.get("data", data),
                 "mockup_urls": mockups_mod.extract_mockup_urls(data)})


@mockup.command("styles")
@click.argument("product_id", type=int)
@click.pass_context
@handle_error
def mockup_styles(ctx, product_id):
    """List mockup styles available for a product."""
    data = mockups_mod.list_styles(get_backend(ctx), product_id)
    output(ctx, data.get("data", data))


@mockup.command("templates")
@click.argument("product_id", type=int)
@click.pass_context
@handle_error
def mockup_templates(ctx, product_id):
    """List mockup templates (positional data) for a product."""
    data = mockups_mod.list_templates(get_backend(ctx), product_id)
    output(ctx, data.get("data", data))


# --------------------------------------------------------------------------
# files
# --------------------------------------------------------------------------

@cli.group()
def files():
    """File library. Note: Printful has no list-files endpoint."""


@files.command("add")
@click.option("--url", required=True, help="URL of the file to add")
@click.option("--filename", default=None)
@click.option("--hidden", is_flag=True, default=False,
              help="Do not show the file in the library UI")
@click.pass_context
@handle_error
def files_add(ctx, url, filename, hidden):
    """Add a file to the library by URL."""
    if ctx.obj.get("dry_run"):
        output(ctx, {"dry_run": True, "would_post": "/v2/files", "url": url},
               message="Dry run — no file added.")
        return
    data = files_mod.add_file(get_backend(ctx), url, filename, visible=not hidden)
    body = data.get("data", data)
    sess = get_session()
    sess.record_file(body.get("id"), url, filename or "")
    output(ctx, body, message=f"File {body.get('id')} added.")


@files.command("get")
@click.argument("file_id", type=int)
@click.pass_context
@handle_error
def files_get(ctx, file_id):
    """Get file details by ID."""
    data = files_mod.get_file(get_backend(ctx), file_id)
    output(ctx, data.get("data", data))


@files.command("list")
@click.pass_context
@handle_error
def files_list(ctx):
    """List files added through this CLI (session-local, not a server query)."""
    result = files_mod.list_added(get_session().files)
    output(ctx, result, table={
        "headers": ["ID", "Filename", "Added"],
        "rows": [[str(f.get("id")), str(f.get("filename") or "-"),
                  str(f.get("added_at"))] for f in result["files"]],
    })


# --------------------------------------------------------------------------
# store
# --------------------------------------------------------------------------

@cli.group()
def store():
    """Store information and reporting."""


@store.command("list")
@click.pass_context
@handle_error
def store_list(ctx):
    """List stores available to the token."""
    data = stores_mod.list_stores(get_backend(ctx))
    summary = stores_mod.summarize_stores(data)
    output(ctx, summary, table={
        "headers": ["ID", "Name", "Type"],
        "rows": [[str(s["id"]), str(s["name"]), str(s["type"])]
                 for s in summary["stores"]],
    })


@store.command("stats")
@click.option("--store-id", "target_store", type=int, required=True)
@click.option("--date-from", required=True, help="YYYY-MM-DD")
@click.option("--date-to", required=True, help="YYYY-MM-DD")
@click.option("--report-types", default="sales_and_costs,profit", show_default=True)
@click.option("--currency", default=None)
@click.pass_context
@handle_error
def store_stats(ctx, target_store, date_from, date_to, report_types, currency):
    """Get store statistics. Range cannot exceed 6 months."""
    data = stores_mod.get_statistics(
        get_backend(ctx), target_store, date_from, date_to, report_types, currency
    )
    output(ctx, data.get("data", data))


@store.command("templates")
@click.option("--limit", default=20, show_default=True)
@click.option("--offset", default=0, show_default=True)
@click.pass_context
@handle_error
def store_templates(ctx, limit, offset):
    """List product templates (v1 — no v2 equivalent)."""
    data = stores_mod.list_templates(get_backend(ctx), limit, offset)
    output(ctx, data)


@store.command("use")
@click.argument("store_id", required=False)
@click.option("--save", is_flag=True, default=False,
              help="Also persist this store as the default in the config file")
@click.pass_context
@handle_error
def store_use(ctx, store_id, save):
    """Set the active store. With no ID, pick one from a list.

    Account-level tokens must choose a store before any store-scoped endpoint
    (orders, shipping rates, cost estimates) will work.
    """
    sess = get_session()

    if store_id is None:
        stores_data = stores_mod.list_stores(get_backend(ctx))
        rows = stores_mod.summarize_stores(stores_data)["stores"]
        if not rows:
            raise ValueError("This token cannot reach any stores.")

        # Never prompt when output is being parsed or stdin is not a terminal —
        # an agent or a pipeline must get data back, not a hung prompt.
        if ctx.obj.get("json") or not sys.stdin.isatty():
            raise ValueError(
                "No store ID given and this is not an interactive terminal.\n"
                "Available stores:\n"
                + "\n".join(f"  {s['id']}  {s['name']} ({s['type']})" for s in rows)
                + "\nRe-run as: store use <STORE_ID>"
            )

        skin = get_skin()
        skin.section("Available stores")
        skin.table(
            ["#", "ID", "Name", "Type"],
            [[str(i + 1), str(s["id"]), str(s["name"]), str(s["type"])]
             for i, s in enumerate(rows)],
        )
        choice = click.prompt(
            f"Select a store [1-{len(rows)}]", type=click.IntRange(1, len(rows))
        )
        selected = rows[choice - 1]
        store_id = str(selected["id"])
        skin.info(f"Selected {selected['name']} ({store_id})")

    sess.set_store(store_id)
    if save:
        cfg = load_config()
        cfg["store_id"] = str(store_id)
        save_config(cfg)

    output(
        ctx,
        {"store_id": str(store_id), "saved_to_config": bool(save)},
        message=(f"Active store set to {store_id}"
                 + (" and saved as the default." if save else
                    ". Add --save to make it the default.")),
    )


# --------------------------------------------------------------------------
# sync
# --------------------------------------------------------------------------

@cli.group()
def sync():
    """Sync products (v1 — not yet in v2)."""


@sync.command("products")
@click.option("--limit", default=20, show_default=True)
@click.option("--offset", default=0, show_default=True)
@click.pass_context
@handle_error
def sync_products(ctx, limit, offset):
    """List sync products."""
    data = sync_mod.list_sync_products(get_backend(ctx), limit, offset)
    output(ctx, data)


@sync.command("get")
@click.argument("sync_product_id", type=int)
@click.pass_context
@handle_error
def sync_get(ctx, sync_product_id):
    """Get one sync product."""
    data = sync_mod.get_sync_product(get_backend(ctx), sync_product_id)
    output(ctx, data)


# --------------------------------------------------------------------------
# draft
# --------------------------------------------------------------------------

@cli.group()
def draft():
    """Build an order across multiple commands before submitting it."""


@draft.command("show")
@click.pass_context
@handle_error
def draft_show(ctx):
    """Show the draft order under construction."""
    sess = get_session()
    output(ctx, {"draft": sess.draft.to_dict(), "summary": sess.draft.summary()})


@draft.command("recipient")
@click.option("--name", default=None)
@click.option("--address1", default=None)
@click.option("--address2", default=None)
@click.option("--city", default=None)
@click.option("--state-code", default=None)
@click.option("--country-code", default=None)
@click.option("--zip", "zip_code", default=None)
@click.option("--email", default=None)
@click.option("--phone", default=None)
@click.pass_context
@handle_error
def draft_recipient(ctx, name, address1, address2, city, state_code, country_code,
                    zip_code, email, phone):
    """Set recipient fields on the draft."""
    sess = get_session()
    fields = {
        "name": name, "address1": address1, "address2": address2, "city": city,
        "state_code": state_code, "country_code": country_code, "zip": zip_code,
        "email": email, "phone": phone,
    }
    if not any(v for v in fields.values()):
        raise ValueError("Pass at least one recipient field to set.")
    sess.draft.set_recipient(**fields)
    sess.touch()
    output(ctx, sess.draft.summary(), message="Recipient updated.")


@draft.command("add-item")
@click.option("--variant-id", type=int, required=True, help="Catalog variant ID")
@click.option("--quantity", type=int, default=1, show_default=True)
@click.option("--image-url", default=None, help="Design file URL for this placement")
@click.option("--placement", default=None, show_default="front")
@click.option("--technique", default=None, show_default="dtg")
@click.option("--external-id", default=None)
@click.pass_context
@handle_error
def draft_add_item(ctx, variant_id, quantity, image_url, placement, technique,
                   external_id):
    """Add a line item to the draft."""
    sess = get_session()
    item = sess.draft.add_item(
        variant_id, quantity, placement, image_url, technique, external_id
    )
    sess.touch()
    output(ctx, {"added": item, "summary": sess.draft.summary()},
           message=f"Added variant {variant_id} x{quantity}.")


@draft.command("remove-item")
@click.argument("index", type=int)
@click.pass_context
@handle_error
def draft_remove_item(ctx, index):
    """Remove a line item from the draft by index."""
    sess = get_session()
    removed = sess.draft.remove_item(index)
    sess.touch()
    output(ctx, {"removed": removed, "summary": sess.draft.summary()},
           message=f"Removed item {index}.")


@draft.command("clear")
@click.pass_context
@handle_error
def draft_clear(ctx):
    """Clear the draft order."""
    sess = get_session()
    sess.draft.clear()
    sess.touch()
    output(ctx, sess.draft.summary(), message="Draft cleared.")


@draft.command("submit")
@click.pass_context
@handle_error
def draft_submit(ctx):
    """Submit the draft as a DRAFT order (not charged)."""
    ctx.invoke(orders_create)


# --------------------------------------------------------------------------
# session
# --------------------------------------------------------------------------

@cli.group("session")
def session_group():
    """Inspect and manage persistent session state."""


@session_group.command("status")
@click.pass_context
@handle_error
def session_status(ctx):
    """Show session state."""
    output(ctx, get_session().status())


@session_group.command("draft")
@click.pass_context
@handle_error
def session_draft(ctx):
    """Show the draft order (alias of `draft show`)."""
    sess = get_session()
    output(ctx, {"draft": sess.draft.to_dict(), "summary": sess.draft.summary()})


@session_group.command("history")
@click.option("--limit", default=10, show_default=True)
@click.pass_context
@handle_error
def session_history(ctx, limit):
    """Show recent commands recorded in the session."""
    history = get_session().history[-limit:]
    output(ctx, {"history": history, "count": len(history)})


@session_group.command("clear")
@click.pass_context
@handle_error
def session_clear(ctx):
    """Clear draft, file records, and history."""
    sess = get_session()
    sess.clear()
    output(ctx, sess.status(), message="Session cleared.")


# --------------------------------------------------------------------------
# config
# --------------------------------------------------------------------------

@cli.group()
def config():
    """Manage stored credentials and defaults."""


@config.command("set")
@click.argument("key")
@click.argument("value")
@click.pass_context
@handle_error
def config_set(ctx, key, value):
    """Set a config value (api_key, store_id)."""
    allowed = {"api_key", "store_id"}
    if key not in allowed:
        raise ValueError(f"Unknown config key '{key}'. Valid keys: {', '.join(sorted(allowed))}")
    cfg = load_config()
    cfg[key] = value
    save_config(cfg)
    shown = "***" if key == "api_key" else value
    output(ctx, {key: shown}, message=f"Set {key}.")


@config.command("get")
@click.argument("key", required=False)
@click.pass_context
@handle_error
def config_get(ctx, key):
    """Show config values. The API token is masked."""
    cfg = load_config()
    if "api_key" in cfg:
        cfg = dict(cfg)
        cfg["api_key"] = "***" + str(cfg["api_key"])[-4:]
    if key:
        output(ctx, {key: cfg.get(key)})
    else:
        output(ctx, cfg or {"note": "No config set."})


@config.command("delete")
@click.argument("key")
@click.pass_context
@handle_error
def config_delete(ctx, key):
    """Delete a config value."""
    cfg = load_config()
    if key not in cfg:
        raise ValueError(f"Config key '{key}' is not set.")
    cfg.pop(key)
    save_config(cfg)
    output(ctx, {"deleted": key}, message=f"Deleted {key}.")


@config.command("path")
@click.pass_context
@handle_error
def config_path(ctx):
    """Show the config file path."""
    output(ctx, {"config_file": str(CONFIG_FILE), "exists": CONFIG_FILE.exists()})


# --------------------------------------------------------------------------
# test
# --------------------------------------------------------------------------

@cli.command("test")
@click.pass_context
@handle_error
def test_connection(ctx):
    """Verify credentials against the live API."""
    backend = get_backend(ctx)
    data = shipping_mod.list_countries(backend)
    count = len(data.get("data", []) or [])
    result = {
        "ok": True,
        "countries_returned": count,
        "store_id": backend.store_id,
        "api_base": "https://api.printful.com/v2",
    }
    output(ctx, result, message=f"Connected. {count} shipping countries available.")


# --------------------------------------------------------------------------
# REPL
# --------------------------------------------------------------------------

REPL_COMMANDS = {
    "catalog": "Browse products, variants, prices, categories, size guides",
    "orders": "List, create, update, cancel, confirm, estimate orders",
    "ship": "Shipping rates, countries, tax",
    "mockup": "Create and check mockups, list styles and templates",
    "files": "Add and inspect design files",
    "store": "Stores, statistics, product templates",
    "sync": "Sync products (v1)",
    "draft": "Build an order step by step",
    "session": "Session status, draft, history, clear",
    "config": "Credentials and defaults",
    "test": "Check API connectivity",
    "help": "Show this help",
    "exit": "Leave the REPL",
}


@cli.command("repl", hidden=True)
@click.pass_context
def repl(ctx):
    """Interactive mode."""
    global _repl_mode
    _repl_mode = True
    skin = get_skin()
    skin.print_banner()
    skin.info("Billable commands (orders confirm/cancel) still require --yes here.")
    try:
        pt_session = skin.create_prompt_session()
    except Exception:
        pt_session = None

    sess = get_session()
    while True:
        try:
            summary = sess.draft.summary()
            context = (f"draft:{summary['item_count']} item(s)"
                       if summary["item_count"] else "")
            line = skin.get_input(pt_session, project_name="printful",
                                  modified=sess._modified, context=context)
        except (EOFError, KeyboardInterrupt):
            break
        if not line:
            continue
        if line in ("exit", "quit", ":q"):
            break
        if line in ("help", "?"):
            skin.help(REPL_COMMANDS)
            continue
        try:
            args = line.split()
            cli.main(args=args, standalone_mode=False, obj=dict(ctx.obj))
        except SystemExit:
            pass
        except click.ClickException as e:
            skin.error(e.format_message())
        except Exception as e:  # pragma: no cover - interactive safety net
            skin.error(str(e))

    if sess._modified:
        try:
            sess.save_session()
            skin.success("Session saved.")
        except Exception as e:
            skin.error(f"Could not save session: {e}")
    skin.print_goodbye()
    _repl_mode = False


def main():
    """Console-script entry point."""
    cli(obj={})


if __name__ == "__main__":
    main()

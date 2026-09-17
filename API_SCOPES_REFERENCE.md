# API Token Scope Recommendations - Quick Reference

## TL;DR - Recommended Setup

### Access Level
```
✅ Account (all stores)  ← Choose this
⚪ A single store
```

### Required Scopes
```
✅ View and manage all orders
✅ View all store information
✅ View and manage all store files
✅ View all store products
⚪ View product templates (only for `printful_list_store_templates`)
```

The first four cover 31 of the 32 registered tools. The one they leave out is
`printful_list_store_templates`, which is why the fifth is listed.

### Optional
```
⚪ View/manage webhooks (no tool calls a webhook endpoint)
⚪ View/manage product templates (one tool needs it — `printful_list_store_templates`)
```

---

## Why These Scopes?

### ✅ View and manage all orders
**Used by** every tool that calls `/orders…` or `/order-estimation-tasks`:
- `printful_create_order` - Create draft orders
- `printful_get_order` - View order details
- `printful_update_order` - Change a draft before confirming it
- `printful_cancel_order` - Cancel an order
- `printful_confirm_order` - Submit orders for fulfillment
- `printful_list_orders` - Browse all orders
- `printful_list_order_items` - List the items on one order
- `printful_list_order_shipments` - Shipments and tracking for one order
- `printful_create_estimation_task` - Start a cost estimate
- `printful_get_estimation_task` - Read the estimate back

**Why "manage"?** Need to create, update, cancel and confirm orders, not just view.

---

### ✅ View all store information
**Used by** every tool that calls `/stores…`:
- `printful_list_stores` - List your Printful stores
- `printful_get_store_stats` - Get sales/profit metrics

**Why "view only"?** We only read store data, never modify settings.

---

### ✅ View and manage all store files
**Used by** every tool that calls `/files…` or `/mockup-tasks`:
- `printful_add_file` - Upload design files
- `printful_get_file` - Check file processing status
- `printful_create_mockup_task` - Generate mockups (needs files)
- `printful_get_mockup_task` - Poll a mockup task for its result

**Why "manage"?** Need to upload files, not just view existing ones.

---

### ✅ View all store products
**Used by** every tool that calls `/store/products…` (v1 API):
- `printful_list_sync_products` - List pre-configured products
- `printful_get_sync_product` - Get sync product details

**Why needed?** Access to sync products (saved product templates).

**Note:** Use "View" not "View and manage" unless you need to modify sync products.

---

## What's NOT Needed

### ⚪ Webhooks
**Not used** - no tool calls a webhook endpoint.
**Safe to skip** unless you plan to manually use webhooks.

### ⚪ Product Templates
**Used by one tool.** `printful_list_store_templates` calls `GET /product-templates`
(v1) — see `src/printful_core/endpoints/stores.py`. The same endpoint backs
`printful store templates` on the CLI.

Skip this scope if you do not use that tool. If you do use it and Printful's
"View product templates" scope is what governs the endpoint, omitting the scope
will make that one tool fail. **This repository does not verify which scope
governs `/product-templates`** — confirming that needs a live call against a token
with the scope withheld, which nothing here performs.

---

## Security Implications

### Minimum Viable Scopes (Most Restrictive)
If you only want to browse the catalog without creating orders:
```
✅ View all store information (catalog browsing is said to use public v2 endpoints —
   see the note under "Catalog" below for how far that is established here)
```

### Read-Only Testing
For testing without making changes:
```
✅ View all orders (not "manage")
✅ View all store information
✅ View all store files (not "manage")
✅ View all store products
⚪ View product templates (only for `printful_list_store_templates`)
```

### Production Use (Recommended)
For order creation and everything else except product templates:
```
✅ View and manage all orders
✅ View all store information
✅ View and manage all store files
✅ View all store products
⚪ View product templates (only for `printful_list_store_templates`)
```

---

## Tools by Scope Requirements

**All 32 registered tools appear below, grouped by the endpoint each one calls.** The
grouping is derived from the `@mcp.tool` registrations in `src/printful_mcp/server.py`
and the request builders in `src/printful_core/endpoints/` — not transcribed. If a tool
is added or removed, this list is what has to move with it.

The *endpoint* each tool calls is a fact about this repository. The *scope* that governs
each endpoint is Printful's, and nothing here verifies it; the headings below name the
scope this document associates with each endpoint family.

### Catalog — `/catalog-products…`, `/catalog-variants…`, `/catalog-categories…` (v2)
- `printful_list_catalog_products`
- `printful_get_product`
- `printful_get_product_variants`
- `printful_get_product_availability`
- `printful_get_size_guide`
- `printful_get_variant_prices`
- `printful_list_categories`
- `printful_get_category`
- `printful_list_mockup_styles`
- `printful_list_mockup_templates`

**Note:** this document has long said the catalog tree works without authentication and
that an API key only raises your rate limit. That is Printful's behaviour, not something
this repository tests — every live test here runs with a key. Treat it as Printful's
documentation rather than as a measurement taken in this tree.

### Geography and shipping — `/countries`, `/shipping-rates` (v2)
- `printful_list_countries`
- `printful_calculate_shipping`

**Note:** `/shipping-rates` is store-scoped in practice. An account-level token must send
`PRINTFUL_STORE_ID`, or the call fails with Printful's store-scope error — see the
`printful-cli` skill and `CLAUDE.md`. So this pair is not as freely anonymous as the
catalog tree.

### Requires: Orders Scope — `/orders…`, `/order-estimation-tasks` (v2)
- `printful_create_order`
- `printful_get_order`
- `printful_update_order`
- `printful_cancel_order`
- `printful_confirm_order`
- `printful_list_orders`
- `printful_list_order_items`
- `printful_list_order_shipments`
- `printful_create_estimation_task`
- `printful_get_estimation_task`

### Requires: Store Information Scope — `/stores…` (v2)
- `printful_list_stores`
- `printful_get_store_stats`

### Requires: Files Scope — `/files…`, `/mockup-tasks` (v2)
- `printful_add_file`
- `printful_get_file`
- `printful_create_mockup_task`
- `printful_get_mockup_task`

### Requires: Store Products Scope — `/store/products…` (v1)
- `printful_list_sync_products`
- `printful_get_sync_product`

### Requires: Product Templates Scope — `/product-templates` (v1)
- `printful_list_store_templates`

### Unclassified — `/tax/rates` (v1)
- `printful_calculate_tax`

Printful's scope list has no entry that obviously governs the v1 tax endpoint, and this
repository does not establish one. It is listed here rather than filed under a guess.

---

## Common Questions

### Q: Can I use "view" instead of "view and manage"?
**A:** Yes, but you'll lose functionality:
- **Orders:** Can only view, not create/confirm
- **Files:** Can only view, not upload
- **Store Products:** Can view but not modify sync products

### Q: What's the difference between "Account" and "Single Store"?
**A:**
- **Account:** Works with all your stores, can switch between them
- **Single Store:** Locked to one store only

**Recommendation:** Use "Account" - it's more flexible and you can still specify which store with `PRINTFUL_STORE_ID`.

### Q: How do I know if my scopes are correct?
**A:** Run the read-only live checks:
```bash
export PRINTFUL_API_KEY=your-key
export PRINTFUL_STORE_ID=your-store-id  # required for an Account-level token
.venv/bin/python -m pytest -m live -k "TestLiveReadOnly"
```

If you get permission errors, you need to add more scopes. This selector only issues `GET`
requests — it exercises the orders and store-information scopes above, but not "View and
manage all store files," since the only live test that touches files sits inside the mockup
class (`TestLiveMockups`), which is skipped unless you also set `PRINTFUL_E2E_MOCKUPS=1`. A
clean pass here does not confirm the files scope; a missing one there would first show up as a
403 from `printful_add_file`.

Running the full `-m live` suite (drop the `-k`) checks more, but it is not a read-only check:
it also runs everything in `TestLiveDraftOrder` (its own source labels the class "Live
writes" — it creates and cancels a real draft order and starts real estimation tasks) plus
`test_live_mcp.py`'s own estimation-task test, and, only with `PRINTFUL_E2E_MOCKUPS=1`, the
mockup and file-upload tests.

### Q: Can I change scopes later?
**A:** Yes! Go to https://www.printful.com/dashboard/api and edit your token's scopes, or create a new token.

---

## Quick Setup Checklist

```
[ ] Go to https://www.printful.com/dashboard/api
[ ] Click "Create API Application"
[ ] Select "Account (all stores)"
[ ] Enable these scopes:
    [ ] View and manage all orders
    [ ] View all store information
    [ ] View and manage all store files
    [ ] View all store products
    [ ] View product templates - only if you use printful_list_store_templates
[ ] Copy the API key
[ ] Add to .env file: PRINTFUL_API_KEY=...
[ ] Test: .venv/bin/python -m pytest -m live -k "TestLiveReadOnly"
    (read-only; does not verify the "View and manage all store files" scope above)
```

Done! 🎉

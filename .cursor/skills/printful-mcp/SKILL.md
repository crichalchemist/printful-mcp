---
name: printful-mcp
description: Automate Printful print-on-demand operations through AI. Use when the user asks about Printful, print-on-demand, POD, product catalogs, orders, mockups, shipping rates, or store management. Helps browse products, create orders, generate mockups, and manage fulfillment.
---

# Printful MCP Automation

Expert guidance for automating Printful print-on-demand workflows using the Printful MCP server's 32 tools.

The tool reference below is kept one-to-one with what the server registers. If you ever doubt
it, your own client's tool list is the authority — ask it what the server advertises rather than
trusting this file's count.

## Quick Reference

**When to use this skill:**
- Browsing Printful's product catalog
- Creating and managing orders
- Generating product mockups
- Calculating shipping rates
- Managing store operations
- Checking product availability
- Uploading design files

## Getting Started with Printful

**Don't have a Printful account yet?** Sign up for free and support this project:

👉 [**Create your free Printful account**](https://www.printful.com/a/purplehorizons) 👈

*Using our affiliate link helps support the development of this MCP server at no extra cost to you.*

Once you have an account:
1. Go to [Printful Dashboard → Settings → API](https://www.printful.com/dashboard/api)
2. Create a new API token with the scopes you need
3. Add your token to your MCP configuration

## Available Tool Categories

| Category | Tools | Common Use Cases |
|----------|-------|------------------|
| 🛍️ **Catalog** | Browse, search, pricing, categories, size guides | "Show me all t-shirts under $15" |
| 📦 **Orders** | Create, update, manage, fulfill, cancel, estimate | "Create order for John in LA" |
| 🚚 **Shipping** | Rates, countries, tax | "How much to ship to UK?" |
| 🖼️ **Mockups** | Generate, check status, styles, templates | "Create mockup with my design" |
| 📁 **Files** | Upload, retrieve | "Upload my logo file" |
| 🏪 **Stores** | List, statistics, product templates | "Show my store sales" |
| 🔄 **Sync** | Legacy products | "List my synced products" |

## Common Workflows

### 1. Product Discovery Workflow

**User asks:** "Find me a product to print my design on"

**Steps:**
1. **Browse catalog** by category or technique
2. **Check availability** for specific variants
3. **Get pricing** in user's currency
4. **Show variants** (sizes/colors)

**Example prompts to use:**
```
"Show me all hoodies available for DTG printing"
"What sizes does product 71 come in?"
"How much is variant 4011 in USD?"
"Is this variant in stock?"
```

### 2. Order Creation Workflow

**User asks:** "Create an order for my customer"

**Steps:**
1. **Create draft order** with recipient details
2. **Add items** (if not done in creation)
3. **Calculate shipping** (optional, for transparency)
4. **Confirm order** to start fulfillment

**Example prompts:**
```
"Create draft order for John Doe, 123 Main St, Los Angeles CA 90001"
"Calculate shipping to that address"
"Confirm order ID 12345"
```

**⚠️ Important:** Orders are created as DRAFTS. Must be explicitly confirmed to start production.

### 3. Mockup Generation Workflow

**User asks:** "Show me how my design looks on a product"

**Steps:**
1. **Create mockup task** with design URL and product details
2. **Wait 10-30 seconds** (mockup generation takes time)
3. **Check task status** to get mockup URLs
4. **Display mockups** to user

**Example prompts:**
```
"Generate mockup for product 71 with my design at https://example.com/design.png"
"Check status of mockup task 597350033"
```

**⚠️ Note:** Mockup generation is async. Always check status after creating task.

### 4. Store Analysis Workflow

**User asks:** "How's my store doing?"

**Steps:**
1. **List stores** (if multiple)
2. **Get statistics** for target store
3. **Present metrics** clearly

**Example prompts:**
```
"Show all my Printful stores"
"What are the sales stats for store 14690720?"
```

## Best Practices

### ✅ Do This

**1. Use natural language queries**
```
✅ "Show me all t-shirts under $15"
✅ "Create order for John at 123 Main St, LA"
✅ "How much to ship to UK?"
```

**2. Check availability before ordering**
```
✅ First: "Is variant 4011 in stock?"
✅ Then: "Create order with variant 4011"
```

**3. Wait for mockup generation**
```
✅ Create task → Wait 15-30s → Check status
❌ Create task → Immediately check status (will be pending)
```

**4. Use external IDs for order tracking**
```
✅ Create order with external_id="my-shop-order-789"
✅ Reference as @my-shop-order-789 later
```

**5. Request markdown format for readability**
```
✅ Every tool takes format="markdown" (default) or format="json"
✅ Use format="json" only for programmatic processing
⚠️ Two exceptions: printful_list_countries takes no arguments at all, and on
   printful_create_mockup_task `format` is the IMAGE format ("jpg" / "png")
```

### ❌ Avoid This

**1. Don't guess product/variant IDs**
```
❌ "Order variant 9999999" (probably doesn't exist)
✅ "Search for hoodies first, then order"
```

**2. Don't skip draft order confirmation**
```
❌ Creating order and assuming it's sent to production
✅ Create draft → Review → Explicitly confirm
```

**3. Don't exceed rate limits**
```
❌ Making 100+ requests in quick succession
✅ Batch operations, space out requests
General limit: 120 requests per 60 seconds
Mockup creation: 10 per 60s for established stores, 2 per 60s for NEW stores,
  with a 60-second lockout once exceeded, plus 20,000 generated files per
  account per 24 hours
```

**4. Treat a rate-limit error as final, not as a prompt to retry**
```
❌ Catching the error and calling again
✅ Reporting it to the user with the wait time from the message
The server does not retry. A 429 is raised immediately, carrying Printful's
Retry-After value, because a silent retry is what walks a new store into the
60-second mockup lockout.
```

**5. Store ID is NOT required for most operations**
```
✅ Catalog, orders, mockups, shipping, files → No store_id needed
✅ Only printful_get_store_stats requires store_id as a parameter
✅ Single-store API tokens work without any store configuration
⚠️ PRINTFUL_STORE_ID env var only needed for multi-store account tokens
```

## Tool Reference

### 🛍️ Catalog Tools

**printful_list_catalog_products**
- Browse the catalog with filters
- Optional: `limit` (default 20, max 100), `offset`, and the comma-separated filters `category_ids`, `colors`, `techniques`, `types`
- ⚠️ **There is no brand filter.** Those four are the only filters that exist, and an unrecognized one is *silently ignored* rather than rejected — so a misspelled or invented filter returns a full, unfiltered list that looks exactly like a filtered one
- Returns: Product list with IDs, names, types, variant counts and techniques — no images and no prices (use `printful_get_variant_prices` for pricing)

**printful_get_product**
- Detailed product information
- Required: `product_id`
- Returns: Name, ID, type, brand, variant count, status, description, available techniques, and placements
- Use: When user wants deep product details

**printful_get_product_variants**
- All size/color combinations
- Required: `product_id`
- Optional: `limit`, `offset`
- Returns: Variant IDs, names, sizes and colors
- Use: "What sizes are available?"

**printful_get_variant_prices**
- Pricing by currency
- Required: `variant_id`
- Optional: `currency` (e.g. USD, EUR, GBP, CAD)
- Use: "How much in euros?"

**printful_get_product_availability**
- Real-time stock status
- Required: `product_id`
- Optional: `techniques` (comma-separated)
- Returns: Available regions, stock levels
- Use: Before creating orders

**printful_list_categories**
- List the catalog's product categories
- Optional: `limit` (default 20), `offset`
- Use: The category IDs it returns are what `printful_list_catalog_products` filters on

**printful_get_category**
- Get one catalog category
- Required: `category_id`
- Use: "What is category 24?"

**printful_get_size_guide**
- Size tables for a catalog product, in inches or centimetres
- Required: `product_id`
- Optional: `unit` (`"inches"` or `"cm"`; omit for the API default)
- Use: "What are the measurements for a size L?"

### 📦 Order Tools

**printful_create_order**
- Create draft order with recipient and items
- Required: `recipient_name`, `recipient_address1`, `recipient_city`, `recipient_country_code`, `recipient_zip`, and `items_json`
- `items_json`: JSON array of items, each with `source`, `catalog_variant_id`, `quantity`, and `placements` carrying the artwork — an item with no design is rejected
- Optional: `recipient_state_code`, `recipient_email`, `recipient_phone`, `external_id`
- ⚠️ `recipient_state_code` is optional *to the tool* but **Printful requires it for US, CA and AU addresses** — omit it there and the API rejects the order
- Returns: Order ID (save this!)

**printful_get_order**
- View order details and status
- Use order ID or @external_id
- Returns: Full order with items, status, tracking

**printful_confirm_order**
- Start production/fulfillment
- ⚠️ **Cannot be undone**
- ⚠️ **Charges your account**
- Use: After reviewing draft order

**printful_list_orders**
- List all orders with filters
- Optional: `limit`, `offset`, `status`
- Use: "Show my recent orders"

**printful_update_order**
- Change a draft order
- Required: `order_id`, `changes_json` (a JSON object of fields to change, e.g. `{"recipient":{"address1":"2 New Street"}}`)
- ⚠️ **Only drafts can be updated.** A confirmed order cannot be edited
- Use: Fixing an address before confirming

**printful_cancel_order**
- Cancel an order
- Required: `order_id` (or `@external_id`)
- ⚠️ **Destructive and cannot be undone.** A draft is discarded; a confirmed order is cancelled only if it has not entered fulfillment
- Use: Only on the user's explicit instruction

**printful_list_order_items**
- List the items on an order
- Required: `order_id` (or `@external_id`)
- Use: "What's in order 12345?"

**printful_list_order_shipments**
- List the shipments for an order, with tracking numbers
- Required: `order_id` (or `@external_id`)
- Use: "Where is my order?"

**printful_create_estimation_task**
- Start a cost estimate for a would-be order — no order is created and nothing is charged
- Required: `recipient_country_code`, `items_json`
- Optional: `recipient_state_code` (Printful requires it for US, CA, AU), `recipient_city`, `recipient_zip`
- Returns: A task ID, immediately — not the costs
- Use: Quoting a total before committing

**printful_get_estimation_task**
- Read the result of a cost estimate
- Required: `task_id` (from `printful_create_estimation_task`)
- Returns: `pending`, `failed`, or the calculated costs
- Use: A few seconds after starting the estimate

### 🚚 Shipping Tools

**printful_calculate_shipping**
- Get shipping rates and delivery times
- Required: `recipient_country_code` **and `items_json`** — a rate cannot be quoted without knowing what is being shipped
- `items_json`: JSON array of items, each with `source`, `catalog_variant_id` and `quantity`. Artwork is not needed to quote a rate, only to place the order
- Optional: `recipient_state_code`, `recipient_city`, `recipient_zip`, `currency`
- Returns: Available carriers and costs

**printful_list_countries**
- Supported countries and states
- Takes no arguments at all — it is the one tool with no parameters, not even `format`
- Use: Validate addresses
- Returns: Country codes, state codes

**printful_calculate_tax**
- Get the tax rate for a destination
- Required: `country_code`
- Optional: `state_code`, `city`, `zip_code`
- Uses API v1; v2 has no tax endpoint
- Use: Showing a customer their all-in total

### 🖼️ Mockup Tools

**printful_create_mockup_task**
- Generate product mockup images
- Required: `product_id`, `variant_ids` (comma-separated), `design_url`
- Optional: `mockup_style_ids` (comma-separated, from `printful_list_mockup_styles`), `placement`, `technique`, `format`
- ⚠️ Here `format` is the **image** format (`"jpg"` / `"png"`), not the response format
- Returns: Task ID (not the mockups yet!)

**printful_get_mockup_task**
- Check generation status
- Required: `task_id`
- Returns: Status + mockup URLs when ready
- Use: 15-30 seconds after creating task

**printful_list_mockup_styles**
- Mockup styles available for a catalog product
- Required: `product_id`
- Use: The style IDs it returns feed `printful_create_mockup_task`

**printful_list_mockup_templates**
- Print-area templates (positional data) for a catalog product
- Required: `product_id`
- Use: Placing artwork precisely within a print area

### 📁 File Tools

**printful_add_file**
- Add a design file to the library by URL
- Required: `url`
- Optional: `filename`, `visible`
- Returns: File ID for later use

**printful_get_file**
- Get file information
- Required: `file_id`
- Returns: URL, status, dimensions
- Use: Check upload status

⚠️ There is no list-files tool, because Printful has no list-files endpoint in either API
version. Keep track of the IDs `printful_add_file` returns.

### 🏪 Store Tools

**printful_list_stores**
- List all your stores
- Use: Multi-store accounts
- Returns: Store IDs, names, types
- ⚠️ **No store_id parameter needed**

**printful_get_store_stats**
- Sales and profit metrics
- Required: `store_id` (get it from `printful_list_stores` first), **`date_from` and `date_to`** — the date range is not optional, and the range cannot exceed 6 months
- Optional: `report_types`, `currency`
- Returns: Revenue, costs, profit
- ⚠️ **This is the ONLY tool that takes store_id as a parameter**

**printful_list_store_templates**
- The store's saved product templates
- Optional: `limit` (default 20), `offset`
- Uses API v1; v2 has no product-templates endpoint
- Use: "What templates have I saved?"

### 🔄 Sync Product Tools (v1 API)

**printful_list_sync_products**
- List products synced to store
- ⚠️ Only works with Printful stores (not Etsy, Shopify, etc.)
- Use: "Show my store products"

**printful_get_sync_product**
- Detailed sync product info
- Returns: Variants, sync status
- Use: "Details on sync product 123"

## Troubleshooting

### "PRINTFUL_API_KEY environment variable is required"
**Solution:** API key not configured in MCP settings
- Check `~/.cursor/mcp.json` or Claude Desktop config
- Ensure `PRINTFUL_API_KEY` is set in `env` section

### "Rate limit exceeded"
**Solution:** Stop and report the wait time — do not retry in a loop
- The error message carries Printful's own `Retry-After` value; wait at least that long
- The server raises on the first 429 and does **not** retry for you. That is deliberate: an
  automatic retry is what turns a mockup rate limit into a 60-second lockout
- General limit: 120 requests per 60 seconds
- Mockup creation: 10 per 60s established / **2 per 60s for new stores**, plus a cap of 20,000
  generated files per account per 24 hours
- Implement pauses between bulk operations

### "Resource not found"
**Solution:** ID doesn't exist or wrong format
- For orders: Use actual order ID or @external_id format
- For products: Browse catalog first to get valid IDs

### "This API endpoint applies only to Printful stores"
**Solution:** Using sync product tools with third-party store
- Sync products only work with native Printful stores
- Not compatible with Etsy, Shopify, WooCommerce stores

### Mockup stuck on "pending"
**Solution:** Wait longer or check for errors
- Normal wait time: 10-30 seconds
- After 2 minutes: Task likely failed, check error message

### mcporter / HTTP bridge param serialization errors
**Problem:** Tools work in Cursor/Claude Desktop but fail via mcporter or other HTTP-to-stdio bridges
**Cause:** Param serialization differs between direct stdio and HTTP bridges

**Solutions:**
1. **Use JSON format** (recommended):
```bash
mcporter call printful_mcp.printful_list_catalog_products --args '{"limit":20}'
mcporter call printful_mcp.printful_get_product --args '{"product_id":71}'
```

2. **Use typed values** (colon syntax for numbers):
```bash
mcporter call printful_mcp.printful_get_product product_id:71
# NOT: product_id=71 (sends string "71" instead of integer 71)
```

3. **Use HTTP transport** (bypasses mcporter's stdio bridge):
```bash
# Start server with HTTP transport
python -m printful_mcp --transport http --port 8000

# Server runs on http://localhost:8000/mcp (StreamableHTTP)
# Connect HTTP-compatible MCP clients directly
```

## Common User Questions

**Q: "Can I browse your catalog?"**
→ Use `printful_list_catalog_products` with filters

**Q: "How much does shipping cost?"**
→ Use `printful_calculate_shipping` with address and items

**Q: "Create an order for my customer"**
→ Use `printful_create_order` → Review → `printful_confirm_order`

**Q: "Show me how my design looks"**
→ Use `printful_create_mockup_task` → Wait → `printful_get_mockup_task`

**Q: "What are my store stats?"**
→ Use `printful_list_stores` then `printful_get_store_stats`

**Q: "Is this product in stock?"**
→ Use `printful_get_product_availability`

## Output Format Guidelines

When presenting results to users:

**For product lists:**
```markdown
Found 5 t-shirts:
1. Bella Canvas 3001 - $5.95 (DTG)
2. Gildan 5000 - $4.50 (DTG)
...
```

**For orders:**
```markdown
Order #12345 created (DRAFT)
- Recipient: John Doe
- Address: 123 Main St, Los Angeles CA 90001
- Status: Draft (not yet sent to production)

Next step: Confirm order to start fulfillment
```

**For shipping rates:**
```markdown
Shipping to UK:
- Standard: $8.50 (7-14 business days)
- Express: $15.00 (3-5 business days)
```

**For errors:**
```markdown
❌ Error: Rate limit exceeded
⏱️ Wait 45 seconds and try again
```

## Advanced Patterns

### Bulk Product Lookup
```
For each product in user's list:
1. Get product details
2. Check availability
3. Get pricing
4. Present summary table
```

### Order Validation Flow
```
1. Calculate shipping first
2. Show customer total cost
3. Get user confirmation
4. Create order
5. Confirm order
```

### Multi-Store Management
```
1. List all stores
2. Get stats for each
3. Compare performance
4. Present consolidated view
```

## API Version Notes

- **Primary:** API v2 (beta, but production-ready)
- **Fallback:** API v1, used only where v2 has no equivalent — sync products
  (`printful_list_sync_products`, `printful_get_sync_product`), product templates
  (`printful_list_store_templates`) and tax rates (`printful_calculate_tax`)
- **Auto-switching:** Server handles version selection
- **Future-proof:** v2 will become standard

Errors read the same either way. Despite what the v2 documentation says about RFC 9457 problem
details, the live API returns the v1-style envelope for 4xx responses, and the server normalizes
both into one readable message.

## Quick Tips

💡 **Always use markdown format** for user-facing results
💡 **Wait 15-30 seconds** after creating mockup tasks
💡 **Confirm orders explicitly** - drafts don't auto-confirm
💡 **Use external IDs** for easier order tracking
💡 **Check availability** before creating orders
💡 **Batch operations** to avoid rate limits
💡 **Validate addresses** with `printful_list_countries` first

## Additional Resources

For detailed documentation:
- [README.md](../../../README.md) - Full setup and usage guide
- [QUICKSTART.md](../../../QUICKSTART.md) - 3-minute setup
- [API_TOKEN_SETUP.md](../../../API_TOKEN_SETUP.md) - API key configuration

For support:
- GitHub Issues: Report bugs or request features
- Printful API Docs: https://developers.printful.com/docs/v2-beta/
- Purple Horizons: https://purplehorizons.io

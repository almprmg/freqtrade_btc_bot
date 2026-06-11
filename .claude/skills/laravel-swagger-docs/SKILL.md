---
name: laravel-swagger-docs
description: Generate or update Swagger/OpenAPI 3 documentation for Laravel APIs that use l5-swagger + zircote/swagger-php attribute syntax. Use when the user asks to write, audit, fix, or update API docs (e.g. "document this controller", "fix swagger gaps", "add swagger annotations", "regenerate api-docs.json"). Audits route↔controller↔doc consistency, fills missing parameters with what+why explanations, and keeps responses honest about envelopes (`success/data/error_code`).
---

# laravel-swagger-docs

Use this skill any time the user wants to **create, audit, fix, or extend** Swagger/OpenAPI documentation for a Laravel project that uses `darkaonline/l5-swagger` with PHP 8 attribute annotations (`OpenApi\Attributes as OA`).

It handles:
- New endpoints that have no annotations yet
- Drift between routes/controllers and the existing docs
- Missing or shallow parameter descriptions ("page" with no rationale)
- Inconsistent response envelopes
- Centralized `app/OpenApi/ApiDocumentation.php` style **and** inline-on-controller style (this codebase uses both)

## Step 0 — Detect the project layout

Before writing anything, learn the project's conventions. Read in this order:

1. `config/l5-swagger.php` — the source of truth for what gets scanned. Check `documentations.default.paths.annotations` (the include list) and `defaults.scanOptions.exclude` (the exclude list). A controller in *both* is double-counted; conflicts crash generation.
2. `routes/api.php` (and any included files) — the actual surface area. **This is the contract Swagger must reflect.** Any route here that has no matching `#[OA\Get|Post|Put|Patch|Delete]` is a documentation gap.
3. `app/Http/Controllers/Api/**` — to see whether docs live inline (per-controller) or in a centralized file like `app/OpenApi/ApiDocumentation.php`.
4. `app/Http/Controllers/Api/V1/BaseController.php` (or equivalent) — find the response helpers (`success`, `error`, `sendResponse`, `sendError`). Their signatures define the **response envelope** (`{success, message, data}` or `{success, message, error_code}`). Docs must match this envelope or they lie.
5. The latest generated `api-docs.json` (or `storage/api-docs/api-docs.json`) — to see what Swagger UI is actually rendering today, before any change.

If both styles coexist (centralized + inline), respect the existing split. Don't migrate one into the other unless the user asks.

## Step 1 — Build the route↔doc matrix

For each route in `routes/api*.php`, check whether a matching `#[OA\<Verb>(path: "...")]` exists in either the centralized file or the controller. Use Grep with a pattern like `path: "/api/v1`. Produce a table:

| Method + path | Documented? | Where | Notes |
|---------------|-------------|-------|-------|

Anything in *Routes* but missing from *Docs* = a gap to fill. Anything documented but no matching route = stale, propose deletion.

## Step 2 — Audit each documented endpoint

For every documented endpoint, open the controller method and confirm:

1. **Path & verb match** — typos like `POST /payments/initate` will silently route nothing.
2. **Path parameters** — every `{id}`, `{slug}`, `{iccid}` in the route must appear as `OA\Parameter(in: "path", required: true)`.
3. **Query parameters** — read every `$request->query(...)`, `$request->input(...)`, `$request->filled(...)`. Each must be an `OA\Parameter(in: "query")` with the right `required` flag and a default that matches the controller's `?? <default>`.
4. **Body parameters** — read the `Validator::make([...])` rules. Build the `OA\RequestBody` schema from the rules: `required` from `required` rule, `type` from `string|integer|boolean|email`, `enum` from `in:a,b,c`, `minimum`/`maximum`/`minLength`/`maxLength` from `min:`/`max:`. **The validator is the contract** — match it exactly.
5. **Response shape** — read what the controller actually returns. If it returns `$this->success(['items' => $x, 'total' => $n])`, the documented shape is `{success, message, data: {items, total}}`, NOT `{success, message, data: [...]}`. Watch for endpoints that bypass the envelope (raw `response()->json([...])`) — flag these as "flat — no `success/data` wrapper".
6. **Error responses** — every `$this->error($msg, $code)` and `$this->sendError($msg, 'CODE', $http)` must appear as an `OA\Response(response: <http>)` with the `error_code` documented. Common codes: `VALIDATION_ERROR`, `NOT_FOUND`, `<DOMAIN>_404`, `ALREADY_*`, `*_EXISTS`, `INVALID_STATUS`, `PAYMENT_FAILED`, `METHOD_UNAVAILABLE`.

## Step 3 — Write parameter descriptions that explain *why*, not just *what*

This is the biggest quality lever. A typical bad description: `"Page number"`. A good one explains the use case:

> `page` — "Page number for paginated traversal (1-indexed). Use this only when iterating through results larger than `per_page`; the response's `meta.has_more` flag tells you when to stop."

For every parameter, the description should answer:
- **What** it controls (the literal effect on the response)
- **When** the client should send it (the use case that justifies its existence)
- **What happens when omitted** (the default behavior)
- **Edge cases or gotchas** (max values, server-side caps, special values like `0`/`null`)

Templates that work:

- **Pagination**: `page` — "1-indexed page index. Combine with `per_page` to traverse results; stop when `meta.has_more` is `false`."
- **Page size**: `per_page` — "Items per page. Default N. Server caps at M to bound query cost — values above M are silently clamped."
- **Search keywords**: `q` — "Free-text search. Matches the `<field>` column with a SQL `LIKE %q%` (case-insensitive on MySQL utf8 collations). Use for type-ahead; for exact lookups prefer the slug-based detail endpoint."
- **Sort**: `sort` — "Result ordering. `latest` (default) returns newest first by `created_at`; `popular` orders by view counter; `top_rated` orders by `reviews_avg_rating`. Combine with filters — sort applies after filtering."
- **Filter by FK id**: `country_id` — "Restrict results to one country. Use the IDs returned by `GET /destinations` or the country list. Omit to search globally."
- **Status enum**: `status` — "Lifecycle filter. `upcoming` includes Pending+Processing (the booking is still actionable). `completed` is the terminal happy state, `cancelled` is the terminal user-aborted state."
- **Boolean**: `featured` — "When truthy (1, true, yes, on), return only items flagged in the admin as featured. Use for the home-screen 'spotlight' rail. Omit for the full catalog."

## Step 4 — Avoid these specific mistakes

These are recurring bugs in Laravel+l5-swagger projects:

1. **Validator says one thing, doc says another.** If the validator allows `package` in `product_type` but the doc enum is `["tour","hotel"]`, mobile clients will get `422` unexpectedly. Always rebuild the enum from `Validator::make`.
2. **Documenting envelope when controller returns flat.** `BaseController::success()` wraps; raw `response()->json()` does not. The login endpoint in many projects bypasses the envelope — say so explicitly: *"Response is flat — no `success/data` wrapper."*
3. **Wrong response wrapping depth.** `$this->success(['items' => $x])` produces `data.items`, not `data: [items]`. The `OA\Property(property: "items", ...)` must be nested **inside** the `data` object property.
4. **Documenting fields that don't exist.** When you write the response schema, scroll back through the controller mapping and copy the exact array keys. Never guess.
5. **Forgetting `security`.** Routes inside `Route::middleware('auth:sanctum')` need `security: [["bearerAuth" => []]]`. Routes outside it must NOT have it (otherwise Swagger UI demands a token unnecessarily).
6. **Per_page silent caps.** Many controllers do `min((int)$request->per_page, 50)`. Document the cap; clients hit it once and waste an afternoon debugging.
7. **Path constraints.** A route like `->where('iccid', '[A-Za-z0-9]+')` constrains the path. Reflect that in the parameter `pattern`/description so SDK generators emit the right validation.
8. **Omitting the optional path detail endpoint param.** A route `/v1/foo/{slug}` needs `OA\Parameter(name: "slug", in: "path", required: true, ...)` even if obvious — Swagger UI will refuse to render the form otherwise.
9. **Duplicate annotations.** If the same path is annotated both inline AND in the centralized file, swagger-php throws `Found multiple Operations`. Keep `config/l5-swagger.php` `exclude` list in sync.
10. **Stale examples.** Examples in the doc should be plausible against the seeded demo data. A `country: "United Arab Emirates"` example with `country_id: 999` looks careless and confuses reviewers.

## Step 5 — Apply edits surgically

Edit attribute blocks with the `Edit` tool, **one operation at a time**. Don't rewrite a whole annotation block when only the `description:` is wrong. Smaller diffs review faster and reduce merge conflicts.

When adding a brand-new annotation block, mirror the existing house style:
- Same indentation depth
- Same `<<<DESC ... DESC` heredoc convention if the project uses it
- Same `operationId` casing (camelCase like `bookingShow`, or domain-prefixed like `authLogin`)
- Same `tags` ordering

## Step 6 — Regenerate and verify

After edits run:

```sh
php artisan l5-swagger:generate
```

If it fails with `Found multiple operations with operation id ...`, two annotations claim the same `operationId` — fix and re-run. If it fails with `Found multiple PathItems for path ...`, the same path is documented in two scanned files — adjust `config/l5-swagger.php` `exclude` or remove the duplicate.

After it succeeds, eyeball:
- `storage/api-docs/api-docs.json` (or wherever the project writes it)
- The Swagger UI route (commonly `/api/documentation`)

If the project has a CI check, run that too. Don't claim "done" without a successful generation.

## Step 7 — Commit and report

When summarizing the change to the user:
- List endpoints touched and the *kind* of fix per endpoint (parameter added, enum corrected, envelope clarified, etc.)
- Call out any **code-vs-doc bugs** you noticed but did not fix (e.g. inconsistent `payment_status` mapping between two methods of the same controller). The user decides whether to fix code or doc.
- Mention any routes you intentionally skipped (e.g. installer routes, admin web routes that aren't part of the public API).

## Quick-start prompts the skill responds to well

- "Audit our swagger docs and tell me what's missing"
- "Add swagger annotations to NewController" (it'll read the controller, validator, and routes, then write the block)
- "Update the bookings docs — `package` was added as a product type"
- "Why does the swagger generator fail?" → it'll inspect the config + scan logs
- "Add `why-to-use` explanations to every query parameter"

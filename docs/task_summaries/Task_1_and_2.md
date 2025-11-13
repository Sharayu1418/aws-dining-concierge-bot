# Task 1 — Knowledge Transfer (KT) Doc

**Scope covered:** Step 0 → Step 2.7 (console-only).
**Region:** `us-east-1` (N. Virginia).
**Audience:** teammates who will reproduce or extend our work.
**Goal:** capture exactly what we did, the roadblocks we hit, the options we considered, and why we chose the final approach—plus how to test each piece.

---

## 1) Global Conventions

### 1.1 Naming & Region

* **Region:** `us-east-1` for *all* resources (S3, API Gateway, Lambda, Lex, SQS, DynamoDB, OpenSearch, SES, EventBridge).
* **Prefix:** `dc-<netid>` to avoid collisions.
  Example resources:

  * S3 website: `dc-site-<netid>`
  * API Gateway: **AI Customer Service API** (swagger import)
  * Lambdas: `LF0-ChatAPI`, `LF1-LexHook`, `LF2-SuggWorker`
  * SQS: `dc-q1-requests`
  * DDB: `yelp-restaurants`
  * OpenSearch: `dc-os-domain` / index `restaurants`
  * Lex bot: `DiningConciergeBot` (alias `prod`)

### 1.2 IAM Roles (created in Step 0)

* `LF0Role-<netid>`, `LF1Role-<netid>`, `LF2Role-<netid>`
  Each starts with **AWSLambdaBasicExecutionRole** only. We attach service-specific permissions later, when those resources exist (prevents “unknown ARN” errors).

---

## 2) Step 1 — Frontend on S3 (Static Website)

### 2.1 Actions Performed

1. **Create S3 bucket** `dc-site-<netid>` (Region `us-east-1`).

   * *Block Public Access (bucket)* → **disabled**.
2. **Enable Static website hosting**

   * Index document: `chat.html` (or `index.html` if your copy uses it).
   * Error document: `chat.html` (temporary).
3. **Bucket policy** to allow public reads:

   ```json
   {
     "Version": "2012-10-17",
     "Statement": [{
       "Sid": "PublicReadForWebsite",
       "Effect": "Allow",
       "Principal": "*",
       "Action": "s3:GetObject",
       "Resource": "arn:aws:s3:::dc-site-<netid>/*"
     }]
   }
   ```
4. **Upload site files**

   * `chat.html` at bucket root.
   * Entire `assets/` folder (preserves `css/`, `js/`, `sdk/`).
5. **Test** by loading the **Bucket website endpoint** (from the Properties tab).

### 2.2 Roadblock & Resolution

* **Issue:** “Your bucket policy changes can’t be saved… public policies are blocked by the BlockPublicPolicy setting.”
  **Cause:** Account or bucket-level **Block Public Access** was still on.
  **Options considered:**

  1. Turn off **Block Public Access** at the *bucket level*.
  2. If still blocked, turn off **Account-level** “Block public bucket policies.”
  3. Alternative (not chosen): use S3 ACLs with Object Ownership settings (public-read objects) without bucket policy.
     **Chosen:** Disable Block Public Access (bucket → off; account → off for public bucket policies if needed). This aligns with assignment requirements for a public static site and keeps permissions simple.

### 2.3 Verification Checklist

* Open **Properties → Static website hosting** shows an endpoint.
* Visiting endpoint loads `chat.html` with no 403/404.
* `assets/*` files return 200 OK.

---

## 3) Step 2 — API Gateway + LF0 (Canned Reply)

### 3.1 LF0 Lambda (initial stub)

**Create Lambda** `LF0-ChatAPI` (Python 3.11) using role `LF0Role-<netid>`.
**Initial code** (canned response, API-Gateway-proxy-compatible):

```python
import json, datetime, uuid

def lambda_handler(event, context):
    body_str = event.get('body') or "{}"
    try:
        body = json.loads(body_str)
    except Exception:
        body = {}

    # Accept either { "message": "hi" } or swagger shape:
    # {"messages":[{"type":"unstructured","unstructured":{"text":"hi"}}]}
    msg = body.get("message")
    if not msg:
        try:
            msgs = body.get("messages", [])
            if msgs and "unstructured" in msgs[-1]:
                msg = msgs[-1]["unstructured"].get("text")
        except Exception:
            pass

    reply_text = "I’m still under development. Please come back later."
    now = datetime.datetime.utcnow().isoformat() + "Z"
    resp = {
        "messages": [{
            "type": "unstructured",
            "unstructured": {
                "id": str(uuid.uuid4()),
                "text": reply_text,
                "timestamp": now
            }
        }]
    }
    return {
        "statusCode": 200,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers":
              "Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token",
            "Access-Control-Allow-Methods": "OPTIONS,POST"
        },
        "body": json.dumps(resp)
    }
```

> **Why this shape?** Our swagger expects/returns `{ "messages": [ { "type": "unstructured", "unstructured": {...} } ] }`. Returning that now means the frontend SDK will work unchanged.

### 3.2 API Gateway (two APIs existed; we standardized)

We had:

* **AI Customer Service API** (swagger-imported)
* **dc-api** (manually created earlier)

**Decision:** Use the **swagger one** to match the SDK and method names. We left `dc-api` for reference but do not generate SDK from it.

**Swagger tweak:** removed `basePath: /v1` to keep the deployed path **`/prod/chatbot`** (simpler URLs).

### 3.3 Import Swagger & Wire to LF0

1. **API Gateway → Import** swagger (with `basePath` removed).
2. Confirm resource `/chatbot` with **POST** is present.
3. **Integration = Lambda Proxy** to `LF0-ChatAPI` (Region `us-east-1`).
4. **Enable CORS** on `/chatbot` (OPTIONS + POST; headers default; origin `*`).
5. **Deploy** to stage `prod`.

> **Design choice:** Lambda **Proxy** integration.
>
> * **Why:** It lets Lambda fully control headers/body. Without proxy, API Gateway wraps the Lambda result in an envelope; the SDK/chat.js expects *only* the swagger body.

### 3.4 SDK Generation & Frontend Wiring (Option 2)

1. **Stages → prod → SDK Generation** → JavaScript → **Generate SDK**.
2. Unzip and **upload** to S3 (overwrite):

   * `assets/js/sdk/apigClient.js`
   * `assets/js/sdk/lib/*`
3. In `chat.html`, the existing line

   ```html
   <script src="./assets/js/sdk/apigClient.js"></script>
   ```

   already points to the SDK, so no HTML change was required.

### 3.5 Tests (layered, end-to-end)

**A. API Gateway Method Test (Console)**

* `Resources → /chatbot → POST → Test` with:

  ```json
  {"messages":[{"type":"unstructured","unstructured":{"text":"hi"}}]}
  ```
* Expect **200** and body **without** the `{statusCode,headers}` wrapper (proxy mode).

**B. `curl` sanity test**

```bash
curl -X POST \
  -H "Content-Type: application/json" \
  -d '{"messages":[{"type":"unstructured","unstructured":{"text":"hi"}}]}' \
  https://<api-id>.execute-api.us-east-1.amazonaws.com/prod/chatbot
```

* Expect a plain swagger response, e.g. `{"messages":[{"type":"unstructured",...}]}`.

**C. Browser (S3 site) test**

* Open the static website endpoint → `chat.html`.
* Open DevTools → **Network**.
* Send “hi”:

  * **Request URL** should point to **AI Customer Service API**’s ID and `/prod/chatbot`.
  * **Status:** 200.
  * **Preview:** JSON with `messages[0].unstructured.text`.
  * **CORS:** Response header includes `Access-Control-Allow-Origin: *`.
* Chat bubble shows the canned reply.

### 3.6 Roadblocks & Resolutions (API ↔ Frontend)

**Issue #1: No “Test” button in Stages**

* **Cause:** Stage view doesn’t provide the tester.
* **Options:**

  1. Use **Resources → Method Execution → Test** (chosen).
  2. Use `curl`/Postman against Invoke URL (also used).
* **Why chosen:** Console Method Test gives direct visibility into request/response and integration mapping.

**Issue #2: Frontend didn’t render even though API returned 200**

* **Symptoms:** Browser Preview showed an *envelope*
  `{ statusCode, headers, body: "…json…" }`.
* **Cause:** POST was using **non-proxy** integration; SDK expects the **pure** swagger body.
* **Options:**

  1. Switch to **Lambda Proxy integration** (chosen).
  2. Patch `chat.js` to unwrap `result.data.body` if present (workaround).
* **Why chosen (Proxy):** Standards-compliant, fewer surprises later (CORS, headers, future Lex responses). Patching JS is fragile and duplicates logic across clients.

**Issue #3: Path mismatches (`/v1/chatbot` vs `/chatbot`)**

* **Cause:** swagger’s `basePath: /v1`.
* **Options:**

  1. Remove `basePath` (chosen).
  2. Keep `/v1` and update all calls/SDK to include it.
* **Why chosen:** Simpler URLs; less room for accidental calls to the wrong path.

**Issue #4: CORS preflight failures**

* **Cause:** Incomplete CORS on method/OPTIONS, or missing CORS headers in Lambda.
* **Fixes chosen:**

  * Enable CORS on `/chatbot` (API GW auto-creates/updates OPTIONS).
  * Return CORS headers from LF0 (defensive).
  * **Redeploy** after any CORS change.

**Issue #5: Two APIs existed (wrong SDK generated)**

* **Symptom:** SDK `invokeUrl` pointed to the wrong API ID.
* **Fix:** Re-generate SDK from **AI Customer Service API** and re-upload to S3; confirm by opening `apigClient.js` and checking `invokeUrl` contains the expected API ID + `/prod`.

---

## 4) Troubleshooting Playbook (Fast Checks)

1. **Which API is the SDK calling?**
   Open `assets/js/sdk/apigClient.js` (in S3) → search `invokeUrl`. Confirm the API ID matches **AI Customer Service API** and path `/prod`.
2. **Proxy integration enabled?**
   API → Resources → `/chatbot` → POST → Integration Request shows **Use Lambda Proxy integration** checked.
3. **CORS configured & deployed?**
   Actions → Enable CORS → OPTIONS + POST; then **Deploy** stage.
4. **Lambda returning swagger body?**
   Response has only `{ "messages": [...] }` (no envelope) when proxy is on.
   (We also include headers in Lambda for safety.)
5. **200 but still no UI?**
   Inspect **Network → Preview** to ensure `messages[0].unstructured.text` exists.
   If not, the Lambda response shape or SDK target is wrong.
6. **500 errors?**
   CloudWatch Logs → `LF0-ChatAPI` for stack traces (usually JSON parsing if wrong event format).

---

## 5) Deliverables Captured So Far

* **S3**

  * Static website hosting screenshot (endpoint visible).
  * Bucket policy showing public read.
  * Objects view showing `chat.html` and `assets/` (including `sdk/`).
* **Lambda**

  * `LF0-ChatAPI` code screenshot and successful test.
* **API Gateway**

  * Resources view: `/chatbot` (POST, OPTIONS).
  * Integration Request showing **Lambda Proxy** to `LF0-ChatAPI`.
  * CORS settings (OPTIONS/POST; `*` origin).
  * Stage `prod` with Invoke URL.
  * Method Test result 200 with swagger body.
* **SDK**

  * `apigClient.js` uploaded to S3 (and `lib/`), verified `invokeUrl` has correct API ID.
* **Browser**

  * DevTools Network: POST `/chatbot` 200, Preview shows swagger body, chat UI displays canned reply.

---

## 6) Appendix — Console Clickpaths (Quick Reference)

* **S3 static site:** Bucket → Properties → Static website hosting → Enable; then Permissions → Bucket policy (paste JSON).
* **Lambda Proxy toggle:** API Gateway → APIs → *AI Customer Service API* → Resources → `/chatbot` → POST → Integration Request → **Use Lambda Proxy integration**.
* **CORS enablement:** API Gateway → Resources → select `/chatbot` → Actions → **Enable CORS** (OPTIONS + POST) → **Deploy API**.
* **SDK generation:** API Gateway → Stages → `prod` → **SDK Generation** → JavaScript → Generate → Upload to `assets/js/sdk/` in S3.
* **CloudWatch logs:** Lambda → `LF0-ChatAPI` → Monitor → View logs in CloudWatch.

---

If anyone on the team follows this KT from top to bottom, they should reproduce our exact setup and arrive at a working **S3 → API Gateway → LF0** flow returning the canned reply in the browser, with known pitfalls and their resolutions documented.

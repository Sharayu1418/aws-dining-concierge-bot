# Task 4 — Knowledge Transfer (KT) Doc & RECAP

# Dining Concierge Project — Engineering Runbook (Knowledge Transfer)

This document is the single source of truth for what we built so far (Tasks 1–4) and how to extend to Task 5. It includes architecture, step-by-step procedures, decisions, and every roadblock we hit with the options we considered and why we chose the final fix. Citations point to the assignment spec where a requirement is referenced.

---

## 1) System Overview

**Goal.** Build a serverless Dining Concierge chatbot where a web frontend talks to an API (LF0) that relays user messages to Amazon Lex (bot + LF1). The DiningSuggestionsIntent collects required fields, enqueues a request to SQS, and confirms to the user. Later tasks consume the queue, search ElasticSearch + DynamoDB, and email results.

**Spec highlights.**

* Lex bot with **GreetingIntent, ThankYouIntent, DiningSuggestionsIntent**, handled via **Lambda code hook** so we can validate and format responses.  
* DiningSuggestionsIntent must collect **Location, Cuisine, Dining Time, Number of people, Email**. 
* Push collected parameters to **SQS (Q1)** and **confirm to the user**. 
* Integrate Lex into the chat API so LF0 **extracts message → calls Lex → returns Lex response**. 

---

## 2) Current Architecture (Tasks 1–4)

**Frontend (S3 static site).**

* Based on the provided starter; deployed to S3 static hosting.

**API (API Gateway + LF0).**

* Endpoint receives JSON in the “starter swagger” shape.
* LF0 parses body, calls **Lex V2 runtime `recognize_text`**, returns Lex’s reply in the exact swagger response shape. (Task 4 A–B) 

**Bot (Lex V2 + LF1).**

* Intents: GreetingIntent, ThankYouIntent, DiningSuggestionsIntent.
* **Code hooks enabled** for initialization/validation and fulfillment on DiningSuggestionsIntent (and fulfillment on Greeting/ThankYou).
* **LF1** validates slots during dialog, and on fulfillment sends a JSON message to SQS then **confirms to the user**. (Task 3 B, D–F)  

**Queue (SQS Q1).**

* Receives the dining request payload (location, cuisine, diningTime, numberOfPeople, email, optional diningDate, timestamp). (Task 3E) 

---

## 3) What’s Implemented — Chronological Actions

### A) Task 1 — Frontend

1. **Repurposed starter app** to target our API path and payload shape. Hosted in **S3 static website**. 

### B) Task 2 — API + LF0 (Boilerplate first)

1. **API Gateway** created from the provided swagger; **CORS** enabled. 
2. **LF0** returned the required boilerplate (“I’m still under development…”) to unblock end-to-end frontend → API testing. 

### C) Task 3 — Lex Bot with Code Hook (LF1)

1. **Lex bot** created with three intents; trained/tested from console. 
2. **LF1** implemented:

   * **DialogCodeHook**: validates slots, elicits again when invalid.
   * **Fulfillment**: sends structured payload to **SQS Q1** and returns **confirmation** to the user. 
3. DiningSuggestionsIntent slots configured and **required**:

   * `Location`, `Cuisine`, `DiningTime`, `NumberOfPeople`, `Email` (we also carry `DiningDate` for UX). 

### D) Task 4 — Integrate Lex into LF0

1. **Replaced boilerplate** in LF0 with a **Lex call**:

   * Parse `event['body']` for latest message → `recognize_text()` → map Lex reply back to swagger response. 
2. **IAM fix**: attached `lex:RecognizeText` permission to LF0 role (AccessDenied resolved).
3. **Session fix**: **stable sessionId** per browser session (from header/body or localStorage). This preserved the dialog state across multiple user messages to complete slot-filling.
4. **Removed static closing responses** for Greeting/ThankYou so that **LF1** fully owns those responses (meeting “handled in code hook” intent requirement). 
5. **End-to-end test**: Frontend → API → LF0 → Lex → LF1 → Lex → LF0 → Frontend now produces dynamic, intent-aware replies and completes slot collection.

---

## 4) APIs, Schemas & Contracts

### 4.1 LF0 Request/Response (as used by frontend)

* **Request** (frontend → API Gateway → LF0):

  ```json
  {
    "sessionId": "web-uuid-123",                  // optional but recommended
    "messages": [
      {"type":"unstructured","unstructured":{"id":"...", "text":"Hello", "timestamp":"..."}}
    ]
  }
  ```
* **Response** (LF0 → frontend):

  ```json
  {
    "messages": [
      {"type":"unstructured","unstructured":{"id":"...", "text":"Hi there, how can I help?", "timestamp":"..."}}
    ]
  }
  ```

### 4.2 LF0 → Lex `recognize_text` Inputs

* `botId`, `botAliasId`, `localeId="en_US"`, `sessionId=<stable>`, `text=<user message>`. (Task 4 A–B) 

### 4.3 LF1 (Lex code hook) Return Shapes

* **DialogCodeHook**:

  * `ElicitSlot` reply when a slot fails validation (keeps the dialog open).
  * `Delegate` reply when all current slots are valid; Lex continues elicitation.
* **Fulfillment**:

  * `Close` with a final confirmation message to user.

### 4.4 SQS Message Schema (from LF1)

```json
{
  "location": "Manhattan",
  "cuisine": "indian",
  "diningTime": "21:00",
  "numberOfPeople": "7",
  "email": "user@nyu.edu",
  "diningDate": "2026-07-18",
  "timestamp": "2025-10-02T22:17:10.524Z"
}
```

(Produced to **Q1** as required in Task 3E; user confirmation satisfies Task 3F.) 

---

## 5) Roadblocks → Options → Decisions

### 5.1 LF0 AccessDenied on `lex:RecognizeText`

* **Symptom.** Lambda test failed with `AccessDeniedException` on `RecognizeText`.
* **Options considered.**

  1. Attach **AmazonLexFullAccess** to LF0 role.
  2. Create a **least-privilege inline policy** allowing only `lex:RecognizeText` to our bot-alias ARN.
* **Decision.** Use a **scoped inline policy** to satisfy the call while minimizing permissions. Rationale: follows principle of least privilege, still simple to grade.

### 5.2 Frontend replied “Sorry, I didn’t understand that.” after city input

* **Root cause.** LF0 generated a new **sessionId per request** (`uuid4()`), so the second message (“Manhattan”) hit a **new Lex session** with no dialog context.
* **Options considered.**

  1. Store a **stable sessionId** client-side (localStorage) and send with each request.
  2. Derive sessionId from user identity when known.
* **Decision.** **Stable sessionId** from the browser (header or body). Rationale: cheapest fix, preserves context across turns, works with anonymous users.

### 5.3 Couldn’t find Bot ID / Alias ID in Lex console

* **Symptom.** UI shows test alias with `TSTALIASID`, hiding UUID-style IDs.
* **Options.**

  1. Copy **IDs from the URL** in the console (bot editor / alias page).
  2. Use **AWS CLI** `list-bots` / `list-bot-aliases`.
* **Decision.** Use **URL** for convenience; CLI for verification. Rationale: fastest and unblocks LF0 configuration.

### 5.4 Lex intent responses partly defined in console “Closing response”

* **Symptom.** Mixed ownership between console messages and Lambda caused inconsistent behavior and didn’t strictly satisfy “handled in code hook”.
* **Decision.** Remove console closing responses for Greeting/ThankYou and let **LF1** respond. Rationale: meets requirement that intent responses are **handled in code hook**. 

### 5.5 Location slot not understood as “Manhattan”

* **Observation.** In some runs, `AMAZON.City` may not resolve “Manhattan” as a city. (Later mitigated by session fix; also solved in parallel by slot tweaks.)
* **Options.**

  1. Switch to a **custom slot type** `LocationType` with values/synonyms: `Manhattan`, `NYC`, `New York`.
  2. Keep `AMAZON.City`, adjust prompts, and broaden LF1 validation.
* **Decision.** Prefer **custom slot type** to guarantee “Manhattan” acceptance for the assignment’s Manhattan-only scope (still compatible with LF1 validation).

---

## 6) Operational Playbook (How to Test / Debug)

1. **API end-to-end (frontend).**

* DevTools → Network → verify request payload (`messages[].unstructured.text`) and stable `sessionId` (header `x-session-id` or in body).
* Confirm response text matches Lex’s reply.

2. **LF0 in isolation (Lambda console).**

* Test Event 1: “I need restaurant suggestions” with `headers: {"x-session-id": "demo-1"}`.
* Test Event 2: “Manhattan” with the **same** `x-session-id`.

3. **Lex console test.**

* Walk the sample interaction and verify each slot prompt/validation behavior.

4. **SQS verification.**

* SQS → Queue → “Send and receive messages” → **Poll for messages** and inspect the JSON body.

5. **CloudWatch logs.**

* LF0: log the **sessionId**, **user message**, and **Lex raw response** to prove wiring.
* LF1: log `event` and validation decisions for each slot.

---

## 7) Status vs Assignment (Tasks 1–4)

* **Task 1 (Frontend S3):** Complete. 
* **Task 2 (API + LF0 boilerplate):** Complete; later replaced by Lex integration. 
* **Task 3 (Lex + LF1 + SQS + confirmation):** Complete as designed: intents implemented, code hooks used for validation and fulfillment, SQS publish, confirmation message returned.  
* **Task 4 (Integrate Lex into LF0):** Complete — LF0 extracts text, calls Lex, waits, returns Lex reply. 

---

## 8) Appendix — IAM & Config Snippets

**LF0 role (min-privilege for Lex):**

```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Action": ["lex:RecognizeText"],
    "Resource": "arn:aws:lex:us-east-1:<ACCOUNT_ID>:bot-alias/<BOT_ID>/<ALIAS_ID>"
  }]
}
```

**LF1 role (SQS send + logs):**

```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Action": ["sqs:SendMessage","sqs:GetQueueUrl"],
    "Resource": "arn:aws:sqs:us-east-1:<ACCOUNT_ID>:DiningConciergeSQSQueue"
  }]
}
```

**Frontend session id (pseudo-code):**

```js
const sid = localStorage.lexSessionId || (localStorage.lexSessionId = crypto.randomUUID());
// include in body { sessionId: sid } or header 'x-session-id: sid'
```

---

## 9) Quick Triage Guide

* **Frontend shows “Sorry, I didn’t understand that.” after a prompt:**
  Check **stable `sessionId`** is reused; verify LF0 logs show the same session across turns.

* **LF0 failing with AccessDenied:**
  Confirm **role policy** includes `lex:RecognizeText` on the correct bot-alias ARN.

* **City not recognized:**
  Prefer **custom `LocationType`** with “Manhattan” + synonyms; keep LF1 validation.

* **No SQS messages arriving:**
  Verify LF1 **Fulfillment** branch executes (check `invocationSource`), and LF1 role has **SQS send** perms.

---

If anyone on the team follows this KT from top to bottom, they should reproduce our exact setup and arrive at the designated working.
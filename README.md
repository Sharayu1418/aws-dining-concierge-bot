# Dining Concierge Chatbot

A serverless chatbot that collects restaurant preferences in conversation and emails Manhattan suggestions back asynchronously.

`AWS Lambda` `Amazon Lex V2` `API Gateway` `Amazon SQS` `DynamoDB` `Amazon SES` `S3` `Python` `Yelp API`

> Coursework. NYU Cloud Computing, Fall 2025 — Assignment 1, built by a two-person team (Sharayu Rasal, Rohan Gore). The brief is in [`docs/CC_Fall2025_Assignment1.pdf`](docs/CC_Fall2025_Assignment1.pdf); the build notes the team wrote for each task are in [`docs/task_summaries/`](docs/task_summaries/).

---

## What it does

A static chat page on S3 posts to `POST /chatbot`. **LF0** relays the message to a Lex V2 bot and returns its reply. The bot's `DiningSuggestionsIntent` collects five slots — Location, Cuisine, DiningTime, NumberOfPeople, Email — with **LF1** attached as both dialog and fulfillment code hook, rejecting anything outside Manhattan, an unknown cuisine, or a party size outside 1–20.

When the slots are full, LF1 does not look up a restaurant. It pushes the request onto SQS and closes the conversation with "You're all set." **LF2**, triggered by that queue, queries the `yelp-restaurants` DynamoDB table on its `Cuisine-business_id-index` GSI, picks three at random with `random.sample`, and sends them by SES.

![Architecture](docs/architecture.png)

## Components

| File | Role |
|---|---|
| `lambda-functions/LF0-Chat_API.py` | API Gateway handler; `lexv2-runtime.recognize_text`, unwraps the reply, sets CORS |
| `lambda-functions/LF1.py` | Lex code hook — slot validation, `ElicitSlot`/`Delegate`/`Close`, enqueue to SQS on fulfillment |
| `lambda-functions/LF2-Suggestions_Worker.py` | SQS consumer — DynamoDB GSI query, random pick of 3, SES send |
| `other-scripts/yelp/yelp_script.py` | Yelp scraper: 5 cuisines × 200 target, writes JSON and CSV for DynamoDB import |
| `frontend/chat.html`, `assets/` | Chat UI and the generated API Gateway SDK |
| `frontend/swagger/swagger.yaml` | API spec imported into API Gateway |

## The interesting part: the conversation ends before the work starts

The naive version of this bot looks up restaurants inside the Lex fulfillment hook and replies with them. That couples a chat turn to a database query and an email send — Lex has a response deadline, SES can throttle or bounce, and a user watching a typing indicator pays for both.

LF1 instead treats fulfillment as "the request is complete", not "the answer is ready". It writes the five slot values plus a timestamp to SQS and returns immediately:

```python
sqs.send_message(QueueUrl=os.environ['SQS_QUEUE_URL'], MessageBody=json.dumps(message_body))
```

The user gets a confirmation in one turn. LF2 runs on its own clock off the queue, and the result arrives by email — a channel that is already asynchronous, so nothing is waiting on it. The queue also absorbs a burst of requests that DynamoDB and SES would otherwise see all at once.

One small correctness detail sits on the boundary: LF1 lowercases `cuisine` before enqueueing, because the DynamoDB items were loaded with lowercase cuisine values while Lex returns whatever the user typed. Normalizing at the producer means the consumer's `Key('Cuisine').eq(cuisine)` is an exact match rather than a scan-and-filter.

## Running it

There is no infrastructure-as-code here — the AWS resources were created through the console, and [`docs/task_summaries/`](docs/task_summaries/) is the runbook for reproducing them (naming conventions, IAM roles, Lex intents, the Swagger import, the DynamoDB import from S3).

To rebuild the restaurant dataset:

```bash
pip install -r other-scripts/yelp/requirements.txt
# set API_KEY in yelp_script.py
python other-scripts/yelp/yelp_script.py   # → final_yelp_restaurants.{json,csv}
```

Then import the CSV into DynamoDB with `business_id` as the partition key, and add a `Cuisine-business_id-index` GSI — LF2 queries that index, not the table.

Lambda environment variables: `BOT_ID` and `BOT_ALIAS_ID` on LF0, `SQS_QUEUE_URL` on LF1, `DEFAULT_EMAIL` on LF2.

## Limitations

- **The OpenSearch step is not in this repository.** The assignment routes the worker through an OpenSearch index of restaurant IDs; the committed `LF2` queries DynamoDB directly and never calls OpenSearch. The task notes stop at Task 5.
- **LF0 uses one Lex session for everyone.** `session_id = 'user-website-session'` is a literal, so concurrent visitors share a single conversation state.
- **LF2 cannot fail.** Every record is wrapped in a `try/except` that logs and continues, and the handler returns 200 regardless. A failed SES send is therefore deleted from the queue rather than retried or dead-lettered. The commented-out `raise Exception(...)` on line 14 is what forces a message to a DLQ.
- **Validation and data disagree.** LF1 accepts seven cuisines (adding thai and korean); `yelp_script.py` collects five. A valid Thai request produces "no restaurants found".
- **The scraper has no deduplication.** It paginates sequentially and filters incomplete records, but keeps no set of seen `business_id`s — unlike the strategy described in `docs/task_summaries/Task_5.md`. Yelp's API also caps pagination well before an arbitrary target.
- **Addresses are hardcoded.** The SES `Source` and LF2's fallback recipient are literal personal addresses, and in the SES sandbox every recipient must be verified first.
- **The checked-in SDK is not configured.** `frontend/assets/js/sdk/apigClient.js` still has the placeholder `invokeUrl` of `https://abc123.execute-api.us-east-1.amazonaws.com/v1`.
- **No tests.**

import json
import boto3
import os
from boto3.dynamodb.conditions import Key
import random

# --- AWS Clients ---
dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table('yelp-restaurants')
ses = boto3.client('ses', region_name="us-east-1")

def lambda_handler(event, context):
    print("📨 Event received:", json.dumps(event))
    #raise Exception("Simulated failure to test Q1 → Q1-DLQ") - use for xtra credit question
  
    # Load default email from environment variable (fallback if not set)
    default_email = os.environ.get("DEFAULT_EMAIL", "sharyurasal1818@gmail.com")

    for record in event['Records']:
        try:
            body = json.loads(record['body'])
            cuisine = body.get("cuisine", "").lower().strip()
            email = body.get("email", default_email).strip()

            print(f"🔍 Querying for cuisine: '{cuisine}'")

            # --- Query DynamoDB ---
            response = table.query(
                IndexName='Cuisine-business_id-index',
                KeyConditionExpression=Key('Cuisine').eq(cuisine)
            )

            items = response.get('Items', [])
            print(f"✅ Found {len(items)} restaurants for '{cuisine}'")

            # --- Format email message ---
            if not items:
                msg = f"Sorry, no {cuisine.title()} restaurants found in Manhattan."
            else:
                selected = random.sample(items, min(3, len(items)))
                msg = f"🍽️ Here are some {cuisine.title()} restaurant suggestions in Manhattan:\n\n"
                for r in selected:
                    name = r.get('name', 'Unknown')
                    rating = r.get('rating', 'N/A')
                    address = r.get('display_address', 'Address not available')
                    msg += f" {name} — ⭐ {rating}\n📍 {address}\n\n" 
                msg += "Bon appétit!"

            # --- Send email via SES ---
            ses.send_email(
                Source="srr10019@nyu.edu",
                Destination={"ToAddresses": [email]},
                Message={
                    "Subject": {"Data": f"{cuisine.title()} Restaurant Suggestions"},
                    "Body": {"Text": {"Data": msg}}
                }
            )
            print(f"📧 Email sent successfully to {email} for '{cuisine.title()}'")

        except Exception as e:
            print(f"❌ Error processing record: {str(e)}")

    return {
        "statusCode": 200,
        "body": json.dumps("✅ Lambda executed successfully.")
    }

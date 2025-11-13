import json
import os
import boto3

# Initialize the Lex V2 client
lex = boto3.client('lexv2-runtime')

def lambda_handler(event, context):
    # Get the user's message from the API Gateway event
    try:
        body = json.loads(event.get('body', '{}'))
        user_message = body.get('messages', [{}])[0].get('unstructured', {}).get('text', '')
    except Exception as e:
        print(f"Error parsing request body: {e}")
        return { 'statusCode': 400, 'body': json.dumps('Invalid request body') }

    # Get Bot details from environment variables
    bot_id = os.environ.get('BOT_ID')
    bot_alias_id = os.environ.get('BOT_ALIAS_ID')
    locale_id = 'en_US'
    session_id = 'user-website-session' # Using a static session ID for simplicity

    # Send the message to Lex
    response = lex.recognize_text(
        botId=bot_id,
        botAliasId=bot_alias_id,
        localeId=locale_id,
        sessionId=session_id,
        text=user_message
    )

    # Extract the bot's reply from the Lex response
    bot_reply = "Sorry, I had trouble understanding. Please try again."
    if 'messages' in response and response['messages']:
        bot_reply = response['messages'][0]['content']

    # Format the response to send back to the frontend
    api_response = {
        "messages": [
            {
                "type": "unstructured",
                "unstructured": {
                    "text": bot_reply
                }
            }
        ]
    }

    return {
        'statusCode': 200,
        'headers': {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Headers': 'Content-Type',
            'Access-Control-Allow-Methods': 'OPTIONS,POST'
        },
        'body': json.dumps(api_response)
    }

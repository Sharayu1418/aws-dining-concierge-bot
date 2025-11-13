import json
import boto3
import os
from datetime import datetime

# Initialize SQS client
sqs = boto3.client('sqs')

def handle_greeting(event):
    """Handle GreetingIntent"""
    message = "Hi there, how can I help?"
    return close(event, 'Fulfilled', message)


def handle_thank_you(event):
    """Handle ThankYouIntent"""
    message = "You're welcome!"
    return close(event, 'Fulfilled', message)


def handle_dining_suggestions(event):
    """Handle DiningSuggestionsIntent - collects slots and pushes to SQS"""
    
    invocation_source = event['invocationSource']
    slots = event['sessionState']['intent']['slots']
    
    # Validation during slot collection
    if invocation_source == 'DialogCodeHook':
        validation_result = validate_dining_slots(slots)
        if not validation_result['isValid']:
            return elicit_slot(
                event,
                validation_result['violatedSlot'],
                validation_result['message']
            )
        return delegate(event)
    
    # Fulfillment - all slots collected
    if invocation_source == 'FulfillmentCodeHook':
        # Extract slot values
        location = get_slot_value(slots, 'Location')
        cuisine = get_slot_value(slots, 'Cuisine')
        dining_time = get_slot_value(slots, 'DiningTime')
        num_people = get_slot_value(slots, 'NumberOfPeople')
        email = get_slot_value(slots, 'Email')

        # 🪄 Normalize cuisine for DynamoDB (fix)
        if cuisine:
            cuisine = cuisine.lower()   # 👈 this ensures match with lowercase DynamoDB values
        if location:
            location = location.lower() # (optional) consistent for later filtering

        # Push to SQS Queue
        try:
            message_body = {
                'location': location,
                'cuisine': cuisine,
                'diningTime': dining_time,
                'numberOfPeople': num_people,
                'email': email,
                'timestamp': datetime.now().isoformat()
            }
            
            sqs.send_message(
                QueueUrl=os.environ['SQS_QUEUE_URL'],
                MessageBody=json.dumps(message_body)
            )
            
            response_message = (
                f"You're all set. Expect my {cuisine} restaurant suggestions "
                f"for {num_people} people at {dining_time} shortly! "
                f"I'll send them to {email}. Have a good day."
            )
            
        except Exception as e:
            print(f"Error sending to SQS: {str(e)}")
            response_message = "Sorry, I encountered an error processing your request. Please try again."
        
        return close(event, 'Fulfilled', response_message)


def validate_dining_slots(slots):
    """Validate slot values"""
    
    location = get_slot_value(slots, 'Location')
    cuisine = get_slot_value(slots, 'Cuisine')
    num_people = get_slot_value(slots, 'NumberOfPeople')
    
    if location and location.lower() not in ['manhattan', 'nyc', 'new york']:
        return {
            'isValid': False,
            'violatedSlot': 'Location',
            'message': 'Sorry, I currently only have suggestions for Manhattan. Please try Manhattan.'
        }
    
    valid_cuisines = ['japanese', 'chinese', 'italian', 'mexican', 'indian', 'thai', 'korean']
    if cuisine and cuisine.lower() not in valid_cuisines:
        return {
            'isValid': False,
            'violatedSlot': 'Cuisine',
            'message': f'Sorry, I don\'t have suggestions for {cuisine} cuisine. Try one of these: {", ".join(valid_cuisines)}.'
        }
    
    if num_people:
        try:
            num = int(num_people)
            if num < 1 or num > 20:
                return {
                    'isValid': False,
                    'violatedSlot': 'NumberOfPeople',
                    'message': 'Please enter a party size between 1 and 20.'
                }
        except ValueError:
            return {
                'isValid': False,
                'violatedSlot': 'NumberOfPeople',
                'message': 'Please enter a valid number for the party size.'
            }
    
    return {'isValid': True}


def get_slot_value(slots, slot_name):
    """Safely extract slot value"""
    if slots and slot_name in slots and slots[slot_name]:
        if 'value' in slots[slot_name]:
            return slots[slot_name]['value']['interpretedValue']
    return None


def close(event, fulfillment_state, message):
    """Close the session with a message"""
    return {
        'sessionState': {
            'dialogAction': {'type': 'Close'},
            'intent': {
                'name': event['sessionState']['intent']['name'],
                'state': fulfillment_state
            }
        },
        'messages': [{'contentType': 'PlainText', 'content': message}]
    }


def delegate(event):
    """Delegate to Lex to continue"""
    return {
        'sessionState': {
            'dialogAction': {'type': 'Delegate'},
            'intent': event['sessionState']['intent']
        }
    }


def elicit_slot(event, slot_to_elicit, message):
    """Elicit a specific slot"""
    return {
        'sessionState': {
            'dialogAction': {
                'type': 'ElicitSlot',
                'slotToElicit': slot_to_elicit
            },
            'intent': event['sessionState']['intent']
        },
        'messages': [{'contentType': 'PlainText', 'content': message}]
    }


def lambda_handler(event, context):
    """Lex Code Hook Handler for Dining Concierge Bot"""
    print("Event received:", json.dumps(event))
    
    intent_name = event['sessionState']['intent']['name']
    
    if intent_name == 'GreetingIntent':
        return handle_greeting(event)
    elif intent_name == 'ThankYouIntent':
        return handle_thank_you(event)
    elif intent_name == 'DiningSuggestionsIntent':
        return handle_dining_suggestions(event)
    
    return close(event, 'Fulfilled', "I'm not sure how to help with that.")

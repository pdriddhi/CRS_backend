import json
import boto3
import os
import re
from boto3.dynamodb.conditions import Key

cognito = boto3.client('cognito-idp')
dynamodb = boto3.resource('dynamodb')

USERS_TABLE = os.environ['USERS_TABLE']
COGNITO_CLIENT_ID = os.environ['COGNITO_CLIENT_ID']

table = dynamodb.Table(USERS_TABLE)

def lambda_handler(event, context):
    try:
        body = json.loads(event.get('body', '{}'))
        
        mobile_number = body.get('mobile_number')
        password = body.get('password')
        
        if not mobile_number or not password:
            return {
                'statusCode': 400,
                'body': json.dumps({
                    'message': 'mobile_number and password are required'
                })
            }
        
        phone_digits = re.sub(r'\D', '', mobile_number)
        if not re.match(r'^\d{10}$', phone_digits):
            return {
                'statusCode': 400,
                'body': json.dumps({
                    'message': 'Mobile number must be exactly 10 digits'
                })
            }
        
        phone_e164 = f"+91{phone_digits}"
        
        dynamo_response = table.query(
            IndexName='GSI_PHONE',
            KeyConditionExpression=Key('GSI_PHONE_PK').eq(f'PHONE#{phone_e164}')
        )
        
        if not dynamo_response['Items']:
            return {
                'statusCode': 404,
                'body': json.dumps({
                    'message': 'User not found. Please sign up first.'
                })
            }
        
        user_item = dynamo_response['Items'][0]
        user_id = user_item.get('user_id')
        role = user_item.get('role', 'CUSTOMER')
        name = user_item.get('name', '')
        
        try:
            auth_response = cognito.initiate_auth(
                ClientId=COGNITO_CLIENT_ID,
                AuthFlow='USER_PASSWORD_AUTH',
                AuthParameters={
                    'USERNAME': phone_e164,
                    'PASSWORD': password
                }
            )
            
            id_token = auth_response['AuthenticationResult'].get('IdToken')
            access_token = auth_response['AuthenticationResult'].get('AccessToken')
            refresh_token = auth_response['AuthenticationResult'].get('RefreshToken')
            
            response_data = {
                'message': 'Login successful',
                'user_id': user_id,
                'name': name,
                'role': role,
                'phone': phone_e164,
                'id_token': id_token,
                'access_token': access_token,
                'refresh_token': refresh_token,
                'token_type': auth_response['AuthenticationResult'].get('TokenType', 'Bearer'),
                'expires_in': auth_response['AuthenticationResult'].get('ExpiresIn', 3600)
            }
            
            return {
                'statusCode': 200,
                'body': json.dumps(response_data)
            }
            
        except cognito.exceptions.NotAuthorizedException:
            return {
                'statusCode': 401,
                'body': json.dumps({
                    'message': 'Invalid password',
                    'user_id': user_id
                })
            }
        except cognito.exceptions.UserNotFoundException:
            return {
                'statusCode': 404,
                'body': json.dumps({
                    'message': 'User not found in Cognito',
                    'user_id': user_id
                })
            }
        except cognito.exceptions.UserNotConfirmedException:
            return {
                'statusCode': 403,
                'body': json.dumps({
                    'message': 'Please verify your account',
                    'user_id': user_id
                })
            }
        except Exception as e:
            print(f"Cognito error: {str(e)}")
            return {
                'statusCode': 400,
                'body': json.dumps({
                    'message': 'Authentication failed',
                    'error': str(e)
                })
            }
    
    except json.JSONDecodeError:
        return {
            'statusCode': 400,
            'body': json.dumps({
                'message': 'Invalid JSON in request body'
            })
        }
    except Exception as e:
        print(f"Unexpected error: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({
                'message': 'Internal server error',
                'error': str(e)
            })
        }
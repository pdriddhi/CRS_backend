import json
import boto3
import uuid
import os
import re
from boto3.dynamodb.conditions import Key

dynamodb = boto3.resource("dynamodb")
cognito = boto3.client("cognito-idp")

table = dynamodb.Table(os.environ["USERS_TABLE"])
CLIENT_ID = os.environ["COGNITO_CLIENT_ID"]

def lambda_handler(event, context):
    try:
        body = json.loads(event.get("body", "{}"))

        user_name = body.get("user_name")
        phone = body.get("mobile_number")
        password = body.get("password")

        if not user_name or not phone or not password:
            return {
                "statusCode": 400,
                "body": json.dumps({"message": "user_name, mobile_number, password required"})
            }

        phone = re.sub(r'\D', '', phone)
        if not re.match(r'^\d{10}$', phone):
            return {
                "statusCode": 400,
                "body": json.dumps({"message": "Mobile number must be exactly 10 digits"})
            }

        phone_e164 = f"+{phone}"
            
        response = table.query(
            IndexName="GSI_PHONE",
            KeyConditionExpression=Key("GSI_PHONE_PK").eq(f"PHONE#{phone_e164}")
        )

        if response["Items"]:
            user = response["Items"][0]
            return {
                "statusCode": 200,
                "body": json.dumps({
                    "message": "User already registered",
                    "user_id": user["user_id"],
                    "role": user["role"]
                })
            }

        try:
            cognito.sign_up(
                ClientId=CLIENT_ID,
                Username=phone_e164,
                Password=password,
                UserAttributes=[
                    {"Name": "phone_number", "Value": phone_e164},
                    {"Name": "name", "Value": user_name},
                    {"Name": "custom:role", "Value": "CUSTOMER"}
                ]
            )
        except cognito.exceptions.InvalidParameterException as e:
            # If custom:role is not defined, try without it
            if "custom:role" in str(e):
                cognito.sign_up(
                    ClientId=CLIENT_ID,
                    Username=phone_e164,
                    Password=password,
                    UserAttributes=[
                        {"Name": "phone_number", "Value": phone_e164},
                        {"Name": "name", "Value": user_name}
                    ]
                )
            else:
                raise e

        user_id = str(uuid.uuid4())

        table.put_item(
            Item={
                "PK": f"USER#{user_id}",
                "user_id": user_id,
                "name": user_name,
                "phone": phone_e164,
                "phone_digits": phone,
                "GSI_PHONE_PK": f"PHONE#{phone_e164}",
                "role": "CUSTOMER",
                "status": "ACTIVE"
            }
        )

        return {
            "statusCode": 201,
            "body": json.dumps({
                "message": "Customer registered successfully",
                "user_id": user_id,
                "role": "CUSTOMER"
            })
        }

    except Exception as e:
        print("ERROR:", str(e))
        return {
            "statusCode": 500,
            "body": json.dumps({
                "message": "Internal Server Error",
                "error": str(e)
            })
        }

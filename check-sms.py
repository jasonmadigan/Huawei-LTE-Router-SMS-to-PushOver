import os
import json
import gettext
import time
import sys
import http.client, urllib, json

lang = {
    "zh_TW": "zh_TW",
    "zh_HK": "zh_HK",
    "zh_CN": "zh_CN",
    "en_US": "en_US",
}
SET_LANG = os.getenv("LOCALE")
CURRUNT_LOCALE = lang.get(SET_LANG, "en")
t = gettext.translation("messages", "locale", [CURRUNT_LOCALE])
_ = t.gettext

# check if in docker
def runningInDocker():
    try:
        with open("/proc/self/cgroup", "r") as procfile:
            for line in procfile:
                fields = line.strip().split("/")
                if fields[1] == "docker":
                    return True
    except:
        pass
    return False


# For debugging -------
from typing import Any, Callable

sys.path.insert(0, os.path.join(os.path.dirname(__file__), os.path.pardir))
import pprint


def dump(method: Callable[[], Any]) -> None:
    print("==== %s" % method.__qualname__)
    try:
        pprint.pprint(method())
    except Exception as e:
        print(str(e))
    print("")


# --------

# Test and install the required module and load dotenv if not in docker
if not runningInDocker():
    try:
        import huawei_lte_api
    except ImportError:
        print(_("Trying to Install required module: huawei_lte_api"))
        os.system("pip install huawei_lte_api")
    try:
        import dotenv
    except ImportError:
        print(_("Trying to Install required module: python-dotenv"))
        os.system("pip install python-dotenv")
    from dotenv import load_dotenv

    load_dotenv()

from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from huawei_lte_api.Client import Client
from huawei_lte_api.AuthorizedConnection import AuthorizedConnection
from huawei_lte_api.Connection import Connection
from huawei_lte_api.api.User import User
from huawei_lte_api.enums.sms import BoxTypeEnum
import huawei_lte_api.exceptions

# load environment variable from .env file
HUAWEI_ROUTER_IP_ADDRESS = os.getenv("HUAWEI_ROUTER_IP_ADDRESS", "192.168.8.1")
HUAWEI_ROUTER_ACCOUNT = os.getenv("HUAWEI_ROUTER_ACCOUNT", "admin")
HUAWEI_ROUTER_PASSWORD = os.getenv("HUAWEI_ROUTER_PASSWORD", "")
PUSHOVER_TOKEN = os.getenv("PUSHOVER_TOKEN")
PUSHOVER_USER = os.getenv("PUSHOVER_USER")
ROUTER_NAME = os.getenv("ROUTER_NAME", "MyRouter")
CHECK_INTERVAL = int(
    os.getenv("CHECK_INTERVAL", 300)
)  # Default to 300 seconds (5 minutes)


def check_and_forward_sms():
    """Check for unread SMS messages and forward them via Pushover."""
    try:
        # Establish a connection with authorization
        if HUAWEI_ROUTER_PASSWORD == "":
            connection = AuthorizedConnection(f"http://{HUAWEI_ROUTER_IP_ADDRESS}/")
        else:
            connection = AuthorizedConnection(
                f"http://{HUAWEI_ROUTER_ACCOUNT}:{HUAWEI_ROUTER_PASSWORD}@{HUAWEI_ROUTER_IP_ADDRESS}/"
            )
        client = Client(connection)

        # Fetch all messages in the inbox
        print("Checking inbox for messages.")
        sms = client.sms.get_sms_list(
            1, BoxTypeEnum.LOCAL_INBOX, 50, 0, 0, 1
        )  # Adjust to fetch a batch of messages
        messages = sms.get("Messages", {}).get("Message")

        # Exit early if there are no messages
        if not messages:
            print("No messages found in the inbox.")
            return

        # Ensure messages are always treated as a list
        if isinstance(messages, dict):
            messages = [messages]

        for message in messages:
            # Compile the notification message
            device_model = client.device.information()["DeviceName"]
            notification_message = (
                f"SMS from {ROUTER_NAME} (Huawei {device_model}):\n\n"
                f"FROM: {message['Phone']} - DATE: {message['Date']}\n"
                f"CONTENT:\n{message['Content']}\n"
            )
            print(f"+++++++++++\n{notification_message}\n+++++++++++\n")

            # Send the notification to PushOver
            conn = http.client.HTTPSConnection("api.pushover.net:443")
            conn.request(
                "POST",
                "/1/messages.json",
                urllib.parse.urlencode(
                    {
                        "token": PUSHOVER_TOKEN,
                        "user": PUSHOVER_USER,
                        "message": notification_message,
                    }
                ),
                {"Content-type": "application/x-www-form-urlencoded"},
            )
            response = conn.getresponse()
            response_string = response.read().decode("utf-8")
            json_obj = json.loads(response_string)

            if response.status == 200 and json_obj.get("status") == 1:
                # Delete the message after successful processing
                client.sms.delete_sms([int(message["Index"])])
                print(f"Message with Index {message['Index']} deleted.")
            else:
                print("Pushover failed. Reason: " + response.reason)
                print(response_string)

        # Logout after processing all messages
        client.user.logout()

    except huawei_lte_api.exceptions.ResponseErrorLoginRequiredException as e:
        print(_("Session timeout, login again!"))
    except huawei_lte_api.exceptions.LoginErrorAlreadyLoginException as e:
        client.user.logout()
    except Exception as e:
        print(e)
        print(_("There is an error!\nError message:\n{error_msg}").format(error_msg=e))


if __name__ == "__main__":
    print(f"Running with interval: {CHECK_INTERVAL} seconds")
    try:
        while True:
            check_and_forward_sms()
            time.sleep(CHECK_INTERVAL)
    except KeyboardInterrupt:
        print("Exiting script gracefully.")

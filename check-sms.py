import os
import json
import gettext
import time
import sys
import http.client, urllib, json


lang = {
    'zh_TW': "zh_TW",
    'zh_HK': "zh_HK",
    'zh_CN': "zh_CN",
    'en_US': "en_US",
}
SET_LANG = os.getenv("LOCALE")
CURRUNT_LOCALE = lang.get(SET_LANG, "en")
t = gettext.translation('messages', 'locale', [CURRUNT_LOCALE])
_ = t.gettext

# check if in docker
def runningInDocker():
    try:
        with open('/proc/self/cgroup', 'r') as procfile:
            for line in procfile:
                fields = line.strip().split('/')
                if fields[1] == 'docker':
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


# Test and inatall the required module and load dotenv if not in docker
if not runningInDocker():
    try:
        import huawei_lte_api
    except ImportError:
        print(_('Trying to Install required module: huawei_lte_api'))
        os.system('pip install huawei_lte_api')
    try:
        import dotenv
    except ImportError:
        print(_('Trying to Install required module: python-dotenv'))
        os.system('pip install python-dotenv')
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
HUAWEI_ROUTER_IP_ADDRESS = os.getenv("HUAWEI_ROUTER_IP_ADDRESS")
HUAWEI_ROUTER_ACCOUNT = os.getenv("HUAWEI_ROUTER_ACCOUNT")
HUAWEI_ROUTER_PASSWORD = os.getenv("HUAWEI_ROUTER_PASSWORD")
PUSHOVER_TOKEN = os.getenv("PUSHOVER_TOKEN")
PUSHOVER_USER = os.getenv("PUSHOVER_USER")
ROUTER_NAME = os.getenv("ROUTER_NAME")

connection = None
client = None


try:
    # Establish a connection with authorized
    # Will URL format is different for when you have password disabled
    if HUAWEI_ROUTER_PASSWORD == "":
        connection = AuthorizedConnection('http://{}/'.format(HUAWEI_ROUTER_IP_ADDRESS))
    else:
        connection = AuthorizedConnection('http://{}:{}@{}/'.format(HUAWEI_ROUTER_ACCOUNT, HUAWEI_ROUTER_PASSWORD, HUAWEI_ROUTER_IP_ADDRESS))
    client = Client(connection)

    # get first SMS(unread priority)
    sms = client.sms.get_sms_list(1, BoxTypeEnum.LOCAL_INBOX, 1, 0, 0, 1)

    # Exit if no messages
    if sms['Messages'] == None:   
        sys.exit()

    # Exit if the SMS was read
    if int(sms['Messages']['Message']['Smstat']) == 1:     
        sys.exit()

    # For debugging
    #dump(client.sms.get_sms_list)
    #print(client.device.information())
    #print(client.device.basic_information())

    # Compile the message
    device_model = client.device.information()['DeviceName']
    message = 'SMS from ' + ROUTER_NAME + ' (Huawei ' + device_model + ')\n'
    message += 'FROM: ' + sms['Messages']['Message']['Phone'] + ' - '
    message += 'DATE: ' + sms['Messages']['Message']['Date'] + '\n' 
    message += 'CONTENT:\n'
    message += sms['Messages']['Message']['Content']
    print('+++++++++++\n' + message + '\n+++++++++++\n')
        
    # Send notification to PushOver
    conn = http.client.HTTPSConnection("api.pushover.net:443")
    conn.request("POST", "/1/messages.json",
    urllib.parse.urlencode({
        "token": PUSHOVER_TOKEN,
        "user": PUSHOVER_USER,
        "message": message,
    }), { "Content-type": "application/x-www-form-urlencoded" })
    response = conn.getresponse()
    responseString = response.read().decode('utf-8')
    json_obj = json.loads(responseString)  

    if response.status == 200 and json_obj['status'] == 1:
        # Mark as read if successfully sent
        client.sms.set_read(int(sms['Messages']['Message']['Index']))
        print('Pushover notification sent. All good!')
    else:
        print("Pushover failed. Reason: " + response.reason)
        print(responseString)

except huawei_lte_api.exceptions.ResponseErrorLoginRequiredException as e:
    print(_('Session timeout, login again!'))
except huawei_lte_api.exceptions.LoginErrorAlreadyLoginException as e:
    client.user.logout()
except Exception as e:
    print(_('There is an error!\nError message:\n{error_msg}').format(error_msg=e))


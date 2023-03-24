"""
jenkins-job-notifier

This Python application is designed to monitor a specific Jenkins job through the Jenkins API continuously. 
The purpose of this app is to make it easier to keep track of the job status. It raises alarms when certain 
metrics exceed predefined thresholds, and sends notifications to a Microsoft Teams channel via webhook.

"""
import os
import logging
import base64
import datetime
import sys
import asyncio
import requests
import pymsteams
from retry import retry
from dotenv import load_dotenv

print("Loading environment variables...")
load_dotenv()
JENKINS_DOMAIN = os.getenv('JENKINS_DOMAIN')
JENKINS_JOB_NAME = os.getenv('JENKINS_JOB_NAME')
JENKINS_USERNAME = os.getenv('JENKINS_USERNAME')
JENKINS_TOKEN = os.getenv('JENKINS_TOKEN')
TEAMS_WEBHOOK_URL = os.getenv('TEAMS_WEBHOOK_URL')
BUILD_POLL_FREQUENCY_SECONDS = int(os.getenv('BUILD_POLL_FREQUENCY_SECONDS') or 5)
JOB_POLL_FREQUENCY_SECONDS = int(os.getenv('JOB_POLL_FREQUENCY_SECONDS') or 5400)
MAX_ABORTED_BUILDS = int(os.getenv('MAX_ABORTED_BUILDS') or 4)
MAX_EXECUTED_BUILDS = int(os.getenv('MAX_EXECUTED_BUILDS') or 6)
MAX_FAILED_BUILDS = int(os.getenv('MAX_FAILED_BUILDS') or 3)
MAX_RUNNING_BUILDS = int(os.getenv('MAX_RUNNING_BUILDS') or 8)
MAX_RUNNING_BUILD_DURATION_SECONDS = int(os.getenv('MAX_RUNNING_BUILD_DURATION_SECONDS') or 10800)
MAX_ABORTED_BUILD_DURATION_SECONDS = int(os.getenv('MAX_ABORTED_BUILD_DURATION_SECONDS') or 14400)
MAX_FAILED_BUILD_ATTEMPTS = int(os.getenv('MAX_FAILED_BUILD_ATTEMPTS') or 3)

JENKINS_URL = "https://" + JENKINS_DOMAIN
JENKINS_JOB_URL = JENKINS_URL + "/job/" + JENKINS_JOB_NAME
JENKINS_API = JENKINS_JOB_URL + "/api/json?tree=builds[building,result,timestamp,id,fullDisplayName,duration]"
JENKINS_AUTH = base64.b64encode(f"{JENKINS_USERNAME}:{JENKINS_TOKEN}".encode("utf-8")).decode("utf-8") # Encode the API token in base64

# logging configuration
logging.basicConfig(filename=".log",
                    filemode='a',
                    format='%(asctime)s,%(msecs)d %(name)s %(levelname)s %(message)s',
                    datefmt='%H:%M:%S',
                    level=logging.DEBUG)

def notify(title: str, text: str, build_id: int = None) -> None:
    """
    Sends a notification message to Microsoft Teams channel via a webhook.

    Args:
        title: A string representing the title of the notification message.
        text: A string representing the body of the notification message.
        build_id: An optional integer representing the ID of the Jenkins build.
            If provided, a link button to view the build details will be included
            in the message. If not provided, a link button to view the Jenkins
            job details will be included instead. Default is None.

    Returns:
        None

    Raises:
        pymsteams.TeamsWebhookException: If the notification message fails to
            send via the Microsoft Teams webhook.
    """
    try:
        teamsMessage = pymsteams.connectorcard(TEAMS_WEBHOOK_URL)
        teamsMessage.title(title)
        teamsMessage.text(text)
        if build_id:
            teamsMessage.addLinkButton("View Build Details", JENKINS_JOB_URL + "/" + build_id)
        else:
            teamsMessage.addLinkButton("View Job Details", JENKINS_JOB_URL)
        teamsMessage.send()
    except pymsteams.TeamsWebhookException:
        logging.error("Failed to send notification message")
        teamsMessage.printme()

# Decorate the function that makes the requests with the retry decorator
@retry(delay=2, backoff=2, max_delay=30, jitter=(1, 3))
def get_jenkins_builds() -> any:
    """
    Fetches builds from the Jenkins API and returns it as a JSON object.

    Returns:
        A JSON object representing the data fetched from the Jenkins API.

    Raises:
        requests.exceptions.HTTPError: If an HTTP error occurs while fetching the data.

    The function makes a GET request to the Jenkins API endpoint with the specified
    authorization header and timeout. If the request is successful, the response JSON
    data is returned. If an HTTP error occurs, an error is logged and a notification is
    sent via the notify() function. The program is terminated with sys.exit().
    """    
    logging.info("Fetching data from Jenkins API")
    try:
        response = requests.get(JENKINS_API, headers={"Authorization": f"Basic {JENKINS_AUTH}"}, timeout=10)
        response.raise_for_status()
        return reversed(response.json()['builds'])
    except requests.exceptions.HTTPError as error:
        logging.error("Failed to fetch data: %s", str(error))
        notify('Error retrieving ' + JENKINS_JOB_NAME + ' data from Jenkins', 
              'Failed to fetch data from Jenkins API. Please check the log file for more information and ensure that Jenkins is accessible.')
        sys.exit()

def get_build_relative_time(build: any) -> float:
    """
    Calculates the relative time between the current datetime and the timestamp of a Jenkins build.

    Args:
        build: A dictionary representing a Jenkins build, containing a 'timestamp' key with a value in milliseconds.

    Returns:
        The time difference between the current datetime and the build timestamp, in seconds.

    The function calculates the relative time between the current datetime and the timestamp of the specified
    Jenkins build. The build timestamp is converted from milliseconds to seconds by dividing by 1000. The result
    is returned as a float representing the time difference in seconds.
    """
    return datetime.datetime.now().timestamp() - build['timestamp']/1000

def build_is_today(build: any) -> bool:
    """
    Check if the build timestamp corresponds to today's date. The build timestamp is converted from milliseconds 
    to seconds by dividing by 1000.

    Args:
        build: A dictionary representing a Jenkins build, containing a 'timestamp' key with a value in milliseconds.

    Returns:
        True if the build timestamp corresponds to today's date, False otherwise.
    """
    # Convert epoch time to datetime object in local timezone
    dt = datetime.datetime.fromtimestamp(build['timestamp']/1000)

    # Get today's date in local timezone
    today = datetime.datetime.today().date()

    # Check if the date of the datetime object is equal to today's date
    return dt.date() == today

async def check_builds() -> None:
    """
    Polls the Jenkins API for build status and sends notifications for long-running and running, timed out and 
    failed builds. The function sleeps for a fixed interval of BUILD_POLL_FREQUENCY_SECONDS between each API 
    request and runs indefinitely until it is stopped externally.
    """
    display_names_failed = []
    ids_checked = []
    hashes_running = []
                    
    while True:
        logging.info("Checking builds")
        display_names_running = []

        for build in get_jenkins_builds():

            if bool(build['building']):
                display_names_running.append(build['fullDisplayName'])

            if build['id'] not in ids_checked:

                build_relative_time = get_build_relative_time(build)

                if build['result'] == "FAILURE":
                    display_names_failed.append(build['fullDisplayName'])
                    ids_checked.append(build['id'])
                    build_failed_count = display_names_failed.count(build['fullDisplayName'])

                    if build_failed_count >= MAX_FAILED_BUILD_ATTEMPTS and build_is_today(build):
                        notify('Build failed multiple times',
                            build['fullDisplayName'] + " has failed " + str(build_failed_count) + " times.",
                            build['id'])

                elif build_relative_time >= MAX_RUNNING_BUILD_DURATION_SECONDS and bool(build['building']):
                    ids_checked.append(build['id'])
                    notify('Build still running',
                        build['fullDisplayName'] + " has been running for the last " + str(round(float(build_relative_time/3600), 1)) + " hours.",
                        build['id'])

                elif build['duration']/1000 >= MAX_ABORTED_BUILD_DURATION_SECONDS and build['result'] == "ABORTED" and build_is_today(build):
                    ids_checked.append(build['id'])
                    notify('Build has timed out',
                        build['fullDisplayName'] + " aborted after " + str(round(float(build['duration']/3.6e+6), 1)) + " hours.",
                        build['id'])          
        
        """ 
        the following creates a hash of a list of display names for running builds, compares it to a list 
        of existing hashes, and sends a notification if the hash is not already in the list and the number
        of running builds exceeds the defined maximum value. 
        """
        builds_running_hash = hash(str(display_names_running))
        builds_running_count = len(display_names_running)
        if builds_running_hash not in hashes_running:
            hashes_running.append(builds_running_hash)
            if builds_running_count >= MAX_RUNNING_BUILDS:
                notify('Several ' + JENKINS_JOB_NAME + ' builds running',
                    str(builds_running_count) + " builds currently running: " + ', '.join(display_names_running))

        await asyncio.sleep(BUILD_POLL_FREQUENCY_SECONDS)
        
async def check_job() -> None:
    """
    Polls the Jenkins API for job status and sends notifications according to the number of aborted, executed, 
    and failed builds. The function sleeps for a fixed interval of JOB_POLL_FREQUENCY_SECONDS between each API 
    request. The function runs indefinitely until it is stopped externally.
    """    
    while True:
        logging.info("Checking job")
        count_aborted_builds = 0
        count_failed_builds = 0
        count_executed_builds = 0

        for build in get_jenkins_builds():
            build_relative_time = get_build_relative_time(build)

            if build_relative_time <= JOB_POLL_FREQUENCY_SECONDS:
                if build['result'] == "ABORTED":
                    count_aborted_builds += 1
                elif build['result'] == "FAILURE":
                    count_failed_builds += 1
                elif bool(build['building']):
                    count_executed_builds += 1          

        if count_aborted_builds >= MAX_ABORTED_BUILDS:
            notify('Several ' + JENKINS_JOB_NAME + ' builds aborted',
                str(count_aborted_builds) + " builds aborted within the last " + str(round(float(JOB_POLL_FREQUENCY_SECONDS/3600), 1)) + " hours.")
            
        if count_failed_builds >= MAX_FAILED_BUILDS:
            notify('Several ' + JENKINS_JOB_NAME + ' builds failed',
                str(count_failed_builds) + " builds failed within the last " + str(round(float(JOB_POLL_FREQUENCY_SECONDS/3600), 1)) + " hours.")
            
        if count_executed_builds >= MAX_EXECUTED_BUILDS:
            notify('Several ' + JENKINS_JOB_NAME + ' builds executed',
                str(count_executed_builds) + " builds executed within the last " + str(round(float(JOB_POLL_FREQUENCY_SECONDS/3600), 1)) + " hours.")
        
        await asyncio.sleep(JOB_POLL_FREQUENCY_SECONDS)

## Main program runs here
def main():
    loop = asyncio.get_event_loop()
    loop.create_task(check_builds())
    if JOB_POLL_FREQUENCY_SECONDS != -1:
        loop.create_task(check_job())
    loop.run_forever()

if __name__ == "__main__":
    main()

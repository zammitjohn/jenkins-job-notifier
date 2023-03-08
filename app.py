"""
jenkins-job-notifier

This app continuously checks the Jenkins API to monitor a job in a Jenkins pipeline. It raises alarms when
certain metrics exceed predefined thresholds, and sends notifications to a Microsoft Teams channel via webhook.
For more information, see README.

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
JENKINS_API = os.getenv('JENKINS_API')
JENKINS_USERNAME = os.getenv('JENKINS_USERNAME')
JENKINS_TOKEN = os.getenv('JENKINS_TOKEN')
TEAMS_WEBHOOK_URL = os.getenv('TEAMS_WEBHOOK_URL')
LOGS_FILENAME = os.getenv('LOGS_FILENAME')
BUILD_POLL_FREQUENCY_SECONDS = int(os.getenv('BUILD_POLL_FREQUENCY_SECONDS'))
PIPELINE_POLL_FREQUENCY_SECONDS = int(os.getenv('PIPELINE_POLL_FREQUENCY_SECONDS'))
MAX_ABORTED_BUILDS = int(os.getenv('MAX_ABORTED_BUILDS'))
MAX_IN_PROGRESS_BUILDS = int(os.getenv('MAX_IN_PROGRESS_BUILDS'))
MAX_FAILED_BUILDS = int(os.getenv('MAX_FAILED_BUILDS'))
MAX_IN_PROGRESS_BUILD_DURATION_SECONDS = int(os.getenv('MAX_IN_PROGRESS_BUILD_DURATION_SECONDS'))
MAX_ABORTED_BUILD_DURATION_SECONDS = int(os.getenv('MAX_ABORTED_BUILD_DURATION_SECONDS'))
MAX_FAILED_BUILD_ATTEMPTS = int(os.getenv('MAX_FAILED_BUILD_ATTEMPTS'))

# Encode the API token in base64
AUTH_STR = base64.b64encode(f"{JENKINS_USERNAME}:{JENKINS_TOKEN}".encode("utf-8")).decode("utf-8")

# logging configuration
logging.basicConfig(filename=LOGS_FILENAME,
                    filemode='a',
                    format='%(asctime)s,%(msecs)d %(name)s %(levelname)s %(message)s',
                    datefmt='%H:%M:%S',
                    level=logging.DEBUG)

def notify(title: str, text: str) -> None:
    """
    Sends a notification message to a Microsoft Teams channel using a webhook URL.

    Args:
        title (str): The title of the notification message.
        text (str): The body text of the notification message.

    Returns:
        None

    Raises:
        pymsteams.TeamsWebhookException: If an error occurs while sending the message.

    The function attempts to send the notification message to the Teams channel using the
    specified title and text. If an exception occurs, an error is logged and the message is
    printed to the console using the pymsteams printme() function.
    """    
    try:
        teamsMessage = pymsteams.connectorcard(TEAMS_WEBHOOK_URL)
        teamsMessage.title(title)
        teamsMessage.text(text)
        teamsMessage.send()
    except pymsteams.TeamsWebhookException:
        logging.error("Failed to send notification message")
        teamsMessage.printme()

# Decorate the function that makes the requests with the retry decorator
@retry(delay=2, backoff=2, max_delay=30, jitter=(1, 3))
def get_jenkins_data() -> any:
    """
    Fetches data from the Jenkins API and returns it as a JSON object.

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
        response = requests.get(JENKINS_API, headers={"Authorization": f"Basic {AUTH_STR}"}, timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.HTTPError as error:
        logging.error("Failed to fetch data: %s", str(error))
        notify('Jenkins API data fetch failed', 
              'Failed to fetch data from Jenkins API. Please check the log file for more information.')
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
    Polls the Jenkins API for build status and sends notifications for failed, long-running, or timed out builds.

    The function enters an infinite loop and repeatedly fetches build data from the Jenkins API using the get_jenkins_data()
    function. For each build in the list of builds, the function checks if the build ID is in the ids_ignore list. If not,
    the function calculates the relative time since the build started using the get_build_relative_time() function. Depending
    on the build status and duration, the function sends a notification via the notify() function with details of the build and
    its status.

    The function sleeps for a fixed interval of BUILD_POLL_FREQUENCY_SECONDS between each API request.
    The function runs indefinitely until it is stopped externally.
    """
    display_names_failed = []
    ids_ignore = []        
    while True:
        logging.info("Checking builds")
        builds = get_jenkins_data()['builds']
        for build in builds:
            if build['id'] not in ids_ignore:

                build_relative_time = get_build_relative_time(build)

                if build['result'] == "FAILURE" and build_is_today(build):
                    display_names_failed.append(build['fullDisplayName'])
                    ids_ignore.append(build['id'])
                    build_failed_count = display_names_failed.count(build['fullDisplayName'])

                    if build_failed_count >= MAX_FAILED_BUILD_ATTEMPTS:
                        notify('Build failed multiple times',
                            build['fullDisplayName'] + " has failed " + str(build_failed_count) + " times today.")

                elif build_relative_time >= MAX_IN_PROGRESS_BUILD_DURATION_SECONDS and bool(build['building']):
                    ids_ignore.append(build['id'])
                    notify('Build still in progress',
                        build['fullDisplayName'] + " has been building for the last " + str(round(float(build_relative_time/3600))) + " hours.")

                elif build['duration']/1000 >= MAX_ABORTED_BUILD_DURATION_SECONDS and build['result'] == "ABORTED" and build_is_today(build):
                    ids_ignore.append(build['id'])
                    notify('Build has timed out',
                        build['fullDisplayName'] + " aborted after " + str(round(float(build['duration']/3.6e+6),2)) + " hours.")                                      

        await asyncio.sleep(BUILD_POLL_FREQUENCY_SECONDS)
        
async def check_pipeline() -> None:
    """
    Polls the Jenkins API for pipeline build status and sends notifications for aborted, failed, or long-running builds.

    The function enters an infinite loop and repeatedly fetches build data from the Jenkins API using the get_jenkins_data()
    function. For each build in the list of builds, the function checks if the build has been running for less than or equal to
    PIPELINE_POLL_FREQUENCY_SECONDS. If so, the function checks the build result and building status and increments counters
    for aborted, failed, and in-progress builds. After processing all builds, the function checks if any of the counters exceed
    their respective MAX_*_BUILDS thresholds. If so, the function sends a notification via the notify() function with details
    of the builds and their status.

    The function sleeps for a fixed interval of PIPELINE_POLL_FREQUENCY_SECONDS between each API request. 
    The function runs indefinitely until it is stopped externally.
    """    
    while True:
        logging.info("Checking pipeline")
        count_aborted_builds = 0
        count_failed_builds = 0
        count_in_progress_builds = 0
        builds = get_jenkins_data()['builds']

        for build in builds:
            build_relative_time = get_build_relative_time(build)
            if build_relative_time <= PIPELINE_POLL_FREQUENCY_SECONDS:
                if build['result'] == "ABORTED":
                    count_aborted_builds += 1
                elif build['result'] == "FAILURE":
                    count_failed_builds += 1
                elif bool(build['building']):
                    count_in_progress_builds += 1          

        if count_aborted_builds >= MAX_ABORTED_BUILDS:
            notify('Several builds aborted',
                str(count_aborted_builds) + " builds aborted within the last " + str(round(float(PIPELINE_POLL_FREQUENCY_SECONDS/3600))) + " hours.")
            
        if count_failed_builds >= MAX_FAILED_BUILDS:
            notify('Several builds failed',
                str(count_failed_builds) + " builds failed within the last " + str(round(float(PIPELINE_POLL_FREQUENCY_SECONDS/3600))) + " hours.")
            
        if count_in_progress_builds >= MAX_IN_PROGRESS_BUILDS:
            notify('Several builds building',
                str(count_in_progress_builds) + " builds executed within the last " + str(round(float(PIPELINE_POLL_FREQUENCY_SECONDS/3600))) + " hours.")
        
        await asyncio.sleep(PIPELINE_POLL_FREQUENCY_SECONDS)

## Main program runs here
def main():
    loop = asyncio.get_event_loop()
    loop.create_task(check_builds())
    loop.create_task(check_pipeline())
    loop.run_forever()

if __name__ == "__main__":
    main()

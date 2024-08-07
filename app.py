import os
import logging
import base64
import datetime
import sys
import json
import asyncio
import requests
import pymsteams
from retry import retry
from dotenv import load_dotenv

def get_required_env(env: str) -> str:
    """
    Returns the value of the specified environment variable.

    Args:
        env: A string specifying the name of the environment variable to retrieve.

    Returns:
        The value of the specified environment variable.

    If the specified environment variable is not set, the function terminates the program and prints
    an error message to the console.
    """    
    return os.getenv(env) or sys.exit('Missing required environment variable ' + env)

print("Loading environment variables...")
load_dotenv()
JENKINS_DOMAIN = get_required_env('JENKINS_DOMAIN')
JENKINS_JOB_NAME = get_required_env('JENKINS_JOB_NAME')
JENKINS_USERNAME = get_required_env('JENKINS_USERNAME')
JENKINS_TOKEN = get_required_env('JENKINS_TOKEN')
TEAMS_WEBHOOK_URL = get_required_env('TEAMS_WEBHOOK_URL')
BUILD_POLL_FREQUENCY_SECONDS = int(os.getenv('BUILD_POLL_FREQUENCY_SECONDS') or 5)
JOB_POLL_FREQUENCY_SECONDS = int(os.getenv('JOB_POLL_FREQUENCY_SECONDS') or 5400)
MAX_ABORTED_BUILDS = int(os.getenv('MAX_ABORTED_BUILDS') or 4)
MAX_EXECUTED_BUILDS = int(os.getenv('MAX_EXECUTED_BUILDS') or 6)
MAX_FAILED_BUILDS = int(os.getenv('MAX_FAILED_BUILDS') or 3)
MAX_RUNNING_BUILDS = int(os.getenv('MAX_RUNNING_BUILDS') or 8)
MAX_RUNNING_BUILD_DURATION_SECONDS = int(os.getenv('MAX_RUNNING_BUILD_DURATION_SECONDS') or 10800)
MAX_ABORTED_BUILD_DURATION_SECONDS = int(os.getenv('MAX_ABORTED_BUILD_DURATION_SECONDS') or 14400)
MAX_FAILED_BUILD_ATTEMPTS = int(os.getenv('MAX_FAILED_BUILD_ATTEMPTS') or 3)
DATA_DIRECTORY = "data"
DATA_FILE_PATH = os.path.join(DATA_DIRECTORY, "data.json")
JENKINS_URL = "https://" + JENKINS_DOMAIN
JENKINS_JOB_URL = JENKINS_URL + "/job/" + JENKINS_JOB_NAME
JENKINS_API = JENKINS_JOB_URL + "/api/json?tree=builds[building,result,timestamp,id,fullDisplayName,duration]"
JENKINS_AUTH = base64.b64encode(f"{JENKINS_USERNAME}:{JENKINS_TOKEN}".encode("utf-8")).decode("utf-8") # Encode the API token in base64

def notify(title: str, text: str, build_id: int = None) -> None:
    """
    Sends a notification message through a webhook.

    Args:
        title: A string representing the title of the notification message.
        text: A string representing the body of the notification message.
        build_id: An optional integer representing the ID of the Jenkins build.
            If provided, a link button to view the build details will be included
            in the message. If not provided, a link button to view the Jenkins
            job details will be included instead. Default is None.

    Returns:
        None
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

def save_data(json_key: str, data: dict) -> None:
    """
    Saves the given data to a JSON file under the specified key.
    
    Args:
        json_key: The key used to identify the data in the JSON file.
        data: The data to be saved.
        
    Returns:
        None
    """
    try:
        if os.path.isfile(DATA_FILE_PATH):
            # File exists, so load the contents of the current JSON file into a dictionary
            with open(DATA_FILE_PATH, 'r') as file:
                json_data = json.load(file)

            # Data unchanged, so skip saving
            if json_data.get(json_key) == data:
                return None
                            
            # Update the value of a specific key in the dictionary   
            json_data[json_key] = data
        else:
            json_data = {json_key: data}

        # Write the updated dictionary to the JSON file
        with open(DATA_FILE_PATH, "w") as file:
            json.dump(json_data, file, indent=4)
        logging.info("Saved '%s' data", json_key)    
    except Exception as error: 
        logging.warning("Failed to save '%s' data: %s", json_key, str(error))

def load_data(json_key: str) -> dict:
    """
    Loads and returns the data associated with the given key from a JSON file.

    Args:
        json_key: The key used to identify the data in the JSON file.

    Returns:
        Data loaded from the JSON file, or an empty dictionary if loading fails.
    """          
    # Load an return the data from the JSON file
    try:
        # Load the contents of the current JSON file into a dictionary
        with open(DATA_FILE_PATH) as f:
            data = json.load(f)
        logging.info("Loaded '%s' data", json_key)
        return data[json_key]
    except Exception as error: 
        logging.warning("Failed to load '%s' data: %s", json_key, str(error))
        return {}

async def check_builds() -> None:
    """
    Polls the Jenkins API for build status and sends notifications for long-running and running, timed out and 
    failed builds. The function sleeps for a fixed interval of BUILD_POLL_FREQUENCY_SECONDS between each API 
    request and runs indefinitely until it is stopped externally.
    """
    errors_dict = load_data("errors")
    long_running_dict = load_data("longRunning")
    hashes_running = []
                    
    while True:
        logging.info("Checking builds")
        ids_running = []

        for build in get_jenkins_builds():

            if bool(build['building']):
                ids_running.append(build['id'])

            if build['id'] not in errors_dict:
                if build['result'] == "FAILURE":                
                    errors_dict[build['id']] = {
                        "result": build['result'],
                        "fullDisplayName": build['fullDisplayName']
                    }

                    build_failed_count = sum(1 for inner_dict in errors_dict.values() if inner_dict['fullDisplayName'] == build['fullDisplayName'] and inner_dict['result'] == 'FAILURE')
                    if build_failed_count >= MAX_FAILED_BUILD_ATTEMPTS and build_is_today(build):
                        notify('Build failed multiple times',
                            build['fullDisplayName'] + " has failed " + str(build_failed_count) + " times.",
                            build['id'])

                elif build['duration']/1000 >= MAX_ABORTED_BUILD_DURATION_SECONDS and build['result'] == "ABORTED" and build_is_today(build):
                    errors_dict[build['id']] = {
                        "result": build['result'],
                        "fullDisplayName": build['fullDisplayName']
                    }
                    notify('Build has timed out',
                        build['fullDisplayName'] + " aborted after " + str(round(float(build['duration']/3.6e+6), 1)) + " hours.",
                        build['id'])

            if build['id'] not in long_running_dict:
                build_relative_time = get_build_relative_time(build)
                if build_relative_time >= MAX_RUNNING_BUILD_DURATION_SECONDS and bool(build['building']):
                    long_running_dict[build['id']] = {
                        "timestamp": build['timestamp'],
                        "fullDisplayName": build['fullDisplayName']
                    }
                    notify('Build still running',
                        build['fullDisplayName'] + " has been running for the last " + str(round(float(build_relative_time/3600), 1)) + " hours.",
                        build['id'])
 
        """ 
        the following creates a hash of a list of display names for running builds, compares it to a list 
        of existing hashes, and sends a notification if the hash is not already in the list and the number
        of running builds exceeds the defined maximum value. 
        """
        builds_running_hash = hash(str(ids_running))
        builds_running_count = len(ids_running)
        if builds_running_hash not in hashes_running:
            hashes_running.append(builds_running_hash)
            if builds_running_count >= MAX_RUNNING_BUILDS:
                notify('Several ' + JENKINS_JOB_NAME + ' builds running',
                    str(builds_running_count) + " builds currently running.")

        save_data("errors", errors_dict)
        save_data("longRunning", long_running_dict)
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

    # Create the data directory if it does not exist
    os.makedirs(DATA_DIRECTORY, exist_ok=True)

    # logging configuration
    logfile = os.path.join(DATA_DIRECTORY, '.log')
    os.makedirs(os.path.dirname(logfile), exist_ok=True)
    logging.basicConfig(filename=logfile,
                        filemode='a',
                        format='%(asctime)s,%(msecs)d %(name)s %(levelname)s %(message)s',
                        datefmt='%H:%M:%S',
                        level=logging.DEBUG)
    try:
        loop = asyncio.get_event_loop()
        loop.create_task(check_builds())
        if JOB_POLL_FREQUENCY_SECONDS != -1:
            loop.create_task(check_job())
        loop.run_forever()
    except KeyboardInterrupt:
        logging.info("Keyboard interrupt detected, stopping program...")        

if __name__ == "__main__":
    main()

# Jenkins Job Notifier
This Python application is designed to monitor a specific Jenkins pipeline through the Jenkins API continuously. The purpose of this app is to make it easier to keep track of the pipeline status and to be alerted to any issues that may occur spontaneously.

## Features
The jenkins-job-notifier App checks the following metrics and raises alarms:

- Consecutive Failures: The app raises an alarm when the same job fails a number of consecutive times.
- Job Execution Time: The app raises an alarm when a job takes a certain number of hours.
- Timed Out Jobs: The app raises an alarm when a job gets ABORTED after a certain number of hours.
- Multiple Jobs Execution: The app raises an alarm when a number of jobs get executed within a specified timespan.
- Multiple Aborted Jobs: The app raises an alarm when a certain number of jobs get ABORTED within a specified timespan.
- Multiple Job Failures: The app raises an alarm when a number of jobs fail within a specified timespan.

Notifications are sent through a Microsoft Teams webhook.

## Installation and Usage
- Clone the repository or download the source code from GitHub.
- Make sure you have Python 3 installed on your system.
- Install the required packages by running pip install -r requirements.txt in your terminal.
- Update the .env file with the necessary parameters. [See Configuration below](##Configuration).
- Run the app using python app.py.

The app will run in the background and will continuously check the pipeline status. Any errors will be displayed in the log.

## Configuration
In order to set up the environment variables needed for this project, you should create a .env file in the root directory of your project with the following variables:

### Jenkins configuration
- `JENKINS_DOMAIN`: The domain name for your Jenkins server.
- `JENKINS_JOB_NAME`: The name of the Jenkins job you want to monitor.
- `JENKINS_URL`: The URL for your Jenkins server. Example: https://`${JENKINS_DOMAIN}`.
- `JENKINS_API`: The API endpoint for your Jenkins job. Example: `${JENKINS_URL}`/job/`${JENKINS_JOB_NAME}`/api/json?tree=builds[building,result,timestamp,id,fullDisplayName,duration].
- `JENKINS_USERNAME`: The username to use for authentication with your Jenkins server.
- `JENKINS_TOKEN`: The API token to use for authentication with your Jenkins server.

### Teams notifications
- `TEAMS_WEBHOOK_URL`: The URL for the Microsoft Teams webhook you want to use for notifications.

### Log file
- `LOGS_FILENAME`: The name of the log file you want to use. Example: log.

### Polling frequency
- `JOB_POLL_FREQUENCY_SECONDS`: The number of seconds between each polling request for job status. Example: 5.
- `PIPELINE_POLL_FREQUENCY_SECONDS`: The number of seconds between each polling request for pipeline status. Example: 3600 (1 hour).

### Thresholds
#### Pipeline
- `MAX_ABORTED_JOBS`: The maximum number of jobs that can be aborted within `PIPELINE_POLL_FREQUENCY_SECONDS` before triggering an alert. Example: 4.
- `MAX_IN_PROGRESS_JOBS`: The maximum number of jobs that can be in progress within `PIPELINE_POLL_FREQUENCY_SECONDS` before triggering an alert. Example: 6.
- `MAX_FAILED_JOBS`: The maximum number of jobs that can fail within `PIPELINE_POLL_FREQUENCY_SECONDS` before triggering an alert. Example: 2.
#### Jobs
- `MAX_IN_PROGRESS_JOB_DURATION_SECONDS`: The maximum amount of time an in-progress job can take before triggering an alert, in seconds. Example: 10800 (3 hours).
- `MAX_ABORTED_JOB_DURATION_SECONDS`: The maximum amount of time a job can run before being aborted and triggering an alert, in seconds. Example: 14400 (4 hours).
- `MAX_FAILED_ATTEMPTS_JOB`: The maximum number of times a job can fail before triggering an alert. Example: 4.
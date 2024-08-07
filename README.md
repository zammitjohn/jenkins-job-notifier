# Jenkins Job Notifier
This Python application is designed to monitor a specific Jenkins job through the Jenkins API continuously. The purpose of this app is to make it easier to keep track of the job status. It raises alarms when certain metrics exceed predefined thresholds, and sends notifications to Microsoft Teams via Microsoft Power Automate workflows.

## Features
The jenkins-job-notifier app checks the following metrics and raises alarms:

- Consecutive Failures: The app raises an alarm when the same build fails a number of consecutive times.
- Build Execution Time: The app raises an alarm when a build takes a certain number of hours.
- Timed Out Builds: The app raises an alarm when a build gets ABORTED after a certain number of hours.
- Multiple Builds Running: The app raises an alarm when a specified number of builds are running simultaneously.
- Multiple Builds Execution: The app raises an alarm when a number of builds get executed within a specified timespan.
- Multiple Aborted Builds: The app raises an alarm when a certain number of builds get ABORTED within a specified timespan.
- Multiple Build Failures: The app raises an alarm when a number of builds fail within a specified timespan.

Notifications are sent through a webhook.

## Installation and Usage
- Clone the repository or download the source code from GitHub.
- Make sure you have Python 3 installed on your system.
- Install the required packages by running pip install -r requirements.txt in your terminal.
- Create the .env file with the necessary parameters. [See Configuration below](#configuration).
- Run the app using python app.py.
- Alternatively, build the Docker image and run the Docker container with the environment variables loaded from the .env file:
    ```
    docker run --detach --volume $(pwd)/data:/app/data --env-file .env jenkins-job-notifier
    ```

The app will run in the background and will continuously check the job status. Any errors will be displayed in the log.

## Configuration
In order to set up the environment variables needed for this project, you should create a .env file in the root directory of your project with the following variables:

### Jenkins configuration
- `JENKINS_DOMAIN`: The domain name for your Jenkins server.
- `JENKINS_JOB_NAME`: The name of the Jenkins job you want to monitor.
- `JENKINS_USERNAME`: The username to use for authentication with your Jenkins server.
- `JENKINS_TOKEN`: The API token to use for authentication with your Jenkins server.

### Teams notifications
- `TEAMS_WEBHOOK_URL`: The URL for the Microsoft Teams webhook you want to use for notifications.

### Polling frequency
- `BUILD_POLL_FREQUENCY_SECONDS`: The number of seconds between each polling request for build status. Default: 5.
- `JOB_POLL_FREQUENCY_SECONDS`: The number of seconds between each polling request for job status. Default: 5400 (1 hour), disable by setting to -1.

### Thresholds
- `MAX_ABORTED_BUILDS`: The maximum number of builds that can be aborted within `JOB_POLL_FREQUENCY_SECONDS`. Default: 4.
- `MAX_EXECUTED_BUILDS`: The maximum number of builds that can be executed within `JOB_POLL_FREQUENCY_SECONDS`. Default: 6.
- `MAX_FAILED_BUILDS`: The maximum number of builds that can fail within `JOB_POLL_FREQUENCY_SECONDS`. Default: 3.
- `MAX_RUNNING_BUILDS`: The maximum number of running builds. Default: 8.
- `MAX_RUNNING_BUILD_DURATION_SECONDS`: The maximum duration a running build can take, in seconds. Default: 10800 (3 hours).
- `MAX_ABORTED_BUILD_DURATION_SECONDS`: The maximum duration a build can run before being aborted, in seconds. Default: 14400 (4 hours).
- `MAX_FAILED_BUILD_ATTEMPTS`: The maximum number of times a build can fail. Default: 3.

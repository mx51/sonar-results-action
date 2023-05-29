"""
Client for SonarQube Web API
"""

import requests
import sys


class SonarClient:
    """
    SonarClient class
    """

    def __init__(self, sonar_host_url, sonar_token):
        self.sonar_host_url = sonar_host_url
        self.sonar_token = sonar_token

    def get_project_measures(self, sonar_project_key, pull_request_number, measurable_keys):
        # Create request url
        request_url = f"api/measures/component?component={sonar_project_key}&pullRequest={pull_request_number}&metricKeys={measurable_keys}"

        # Call api
        return self.api_call(request_url)

    def get_qualitygate_status(self, sonar_project_key, pull_request_number):
        # Create request url
        request_url = f"api/qualitygates/project_status?projectKey={sonar_project_key}&pullRequest={pull_request_number}"

        # Call api
        return self.api_call(request_url)

    def api_call(self, request_url):
        # Set headers
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.sonar_token}"
        }

        # Call api
        response = requests.get(self.sonar_host_url + request_url, headers=headers)

        # TODO: add handler for response code and errors
        return response.json()

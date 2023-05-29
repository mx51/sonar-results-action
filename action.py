#!/usr/bin/env python3

from configparser import RawConfigParser
from lib.sonar_client import SonarClient

import github
import json
import os
import re
import requests
import signal
import sys


###
# GLOBALS
###

SONAR_LOGO            = '![image](https://github.com/mx51/sonar-results-action/raw/master/images/sonar-logo-s.png) '
PASSED_IMAGE          = '![image](https://github.com/mx51/sonar-results-action/raw/master/images/passed.png) '
FAILED_IMAGE          = '![image](https://github.com/mx51/sonar-results-action/raw/master/images/failed.png) '
SONAR_PROPERTIES      = 'sonar-project.properties'
SONAR_DEFAULT_KEYS    = ['new_coverage', 'new_lines', 'new_code_smells', 'new_bugs']


###
# MAIN METHOD
###

def main():
    # Get event details
    event_json = read_event()
    pr_number = get_pull_request_number(event_json)

    if not pr_number:
        print(' * Not a pull request.')
        sys.exit()

    # Fetch sonar details
    sonar_project_key, results, quality_gate_status = fetch_sonar_results(pr_number)

    # Get github params
    token = get_env_var('GITHUB_TOKEN')
    repo_name = get_env_var('GITHUB_REPOSITORY')

    # Fetch PR details
    gh = github.Github(token)
    repo = gh.get_repo(repo_name)
    pr = repo.get_pull(pr_number)

    # Update PR with comment
    update_pr_comment(pr, sonar_project_key, results, quality_gate_status)

    # Exit based on status
    if quality_gate_status:
        print(' * Quality Gate: PASSED')
    else:
        print(' * Quality Gate: FAILED')
        sys.exit(1)


# Update PR with sonar scan comment
def update_pr_comment(pr, sonar_project_key, results, quality_gate_status):
    # Retrieve most recent sonar scan comment to avoid duplicates
    issue_comment = None

    for c in pr.get_issue_comments().reversed:
        if SONAR_LOGO in c.body:
            issue_comment = c
            break

    # Check comment for result hash
    pr_result_hash = extract_result_hash(issue_comment)

    # Check if result hashes match
    result_hash = generate_result_hash(results)

    if pr_result_hash == result_hash:
        # Do not recreate duplicate comment
        print(' * Sonar scan results comment already exists. No update.')
        return

    # Note: new comments will be added each time scan results change
    print(' * Creating PR comment with latest sonar scan results')

    # Create comment body
    comment_body = generate_comment_body(sonar_project_key, result_hash, results, quality_gate_status, pr.number)

    # Create or update pull request comment
    if issue_comment:
        issue_comment.edit(comment_body)
    else:
        pr.create_issue_comment(comment_body)


# Create PR comment body
def generate_comment_body(sonar_project_key, result_hash, results, quality_gate_status, pr_number):
    # Check pass/fail image
    status_image = PASSED_IMAGE if quality_gate_status else FAILED_IMAGE

    # Begin comment
    project_link = generate_project_link("dashboard", sonar_project_key, pr_number)
    comment = f'{SONAR_LOGO}  **[Scan Results]({project_link})**:\n\n'

    # Add pass/fail image
    comment += f'[{status_image}]({project_link})\n\n'

    # Start table header
    comment += '| Metric | This PR |\n|-------|--------------|\n'

    for metric in results:
        key = metric['metric']
        new_value = metric['new_value']

        # Special treatment for '-' value
        if new_value == '-':
            new_value = 'No result'

        # Special treatment for 'coverage' metric key
        if 'coverage' in key:
            new_value = format_percentage(new_value)

        # Create line item
        comment += result_line_item(sonar_project_key, key, new_value, pr_number)

    # Append result hash
    comment += result_hash

    # Return comment
    return comment.rstrip()


# Format to one decimal place
def format_percentage(value):
    try:
        return '{:.1f}'.format(float(value)) + '%'  # include percentage character

    except ValueError:
        return value


# Create a line item for Github comment table
def result_line_item(sonar_project_key, key_name, new_value, pr_number):
    # Use 'new_*' key for metric link if result available
    metric_ref = key_name if new_value == '-' else f'new_{key_name}'

    # Generate key_name link
    base_url = generate_project_link("component_measures", sonar_project_key, pr_number)
    key_url = f'{base_url}&metric={metric_ref}'

    # Generate line item
    return f'| [{key_name}]({key_url}) | {new_value} |\n'


# Create result string as hidden text
def generate_result_hash(results):
    # Start new results table
    values = []

    # Iterate through metric keys
    for metric in results:
        key = metric['metric']
        new_value = metric['new_value']

        # Store result
        values.append(f'{key},{new_value}')

    # Return result
    hash_str = '|'.join(values)
    return f'<!-- sonar_results: "{hash_str}" -->'


# Extract result_hash value from comment_body
def extract_result_hash(issue_comment):
    # Check issue comment
    if not issue_comment:
        return '(not found)'

    # Get comment body
    comment_body = issue_comment.body

    # Check for HTML comment string
    comment_search = re.search('(<!-- sonar_results: .* -->)', comment_body)

    if comment_search:
        return comment_search.group(1)

    # Comment hash not found
    return '(not found)'


# Fetch sonar results
def fetch_sonar_results(pr_number):
    # Get sonar project key
    sonar_project_key = read_sonar_project_key()

    # Get sonar details
    sonar_url = get_env_var('SONAR_HOST_URL')
    sonar_token = get_env_var('SONAR_TOKEN')

    # Create sonar client
    sonar_client = SonarClient(sonar_url, sonar_token)

    # Get project metric values
    measures = fetch_project_measures(sonar_client, sonar_project_key, SONAR_DEFAULT_KEYS, pr_number)

    # Note available keys from returned measures
    available_keys = [m['metric'] for m in measures]

    # Parse results
    results = []
    for key in SONAR_DEFAULT_KEYS:
        new_value = 'No result'

        # Check if this 'key' has a corresponding 'new_key' result
        if key in available_keys:
            new_value = extract_result(key, measures)

        # Store result as dict
        results.append({'metric': key, 'new_value': new_value})

    # Check quality gate status
    quality_gate_passed = fetch_quality_gate_status(sonar_client, sonar_project_key, pr_number)

    # Log results for action output
    print(f' * Sonar scan results  : {results}')
    print(f' * Quality gate passed : {quality_gate_passed}')

    # Return results
    return sonar_project_key, results, quality_gate_passed


def fetch_quality_gate_status(sonar_client, sonar_project_key, pr_number):
    # Check quality gate
    qg_status = sonar_client.get_qualitygate_status(sonar_project_key, pr_number)

    if "projectStatus" in qg_status:
        if "status" in qg_status["projectStatus"]:
            return qg_status["projectStatus"]["status"] == "OK"

    return False


# Get metrics for project
def fetch_project_measures(sonar_client, sonar_project_key, measurable_keys, pr_number):
    # Prepare metric key query
    measurable_keys_str = ','.join(measurable_keys)

    # Call sonar
    component = sonar_client.get_project_measures(sonar_project_key, pr_number, measurable_keys_str)
    return component['component']['measures']


# Extract result values
def extract_result(key, measures):
    # Check for result
    for metric in measures:
        if metric['metric'] == key:
            if 'period' in metric:
                return metric['period']['value']
            else:
                return metric['value']

    # No result
    return 'No result'


# Read sonar-project.properties file
def read_sonar_project_key():
    # Get path to sonar properties
    workspace_path = get_env_var('GITHUB_WORKSPACE')
    sonar_properties = f'{workspace_path}/{SONAR_PROPERTIES}'

    # Read sonar properties
    with(open(sonar_properties, 'r')) as f:
        for prop in [line.rstrip() for line in f]:
            name, value = prop.split('=')

            # Check property
            if name == 'sonar.projectKey':
                return value

    # Something went wrong
    print(f'error: sonar.projectKey value not found in sonar properties file: {SONAR_PROPERTIES}')
    sys.exit(1)


# Get link for sonar project
def generate_project_link(page, sonar_project_key, pr_number):
    # Generate url
    base_url = get_env_var('SONAR_HOST_URL')

    # Return result
    return f'{base_url}{page}?id={sonar_project_key}&pullRequest={pr_number}'


# Get PR number from event details
def get_pull_request_number(event_json):
    # Inspect json payload
    if 'pull_request' in event_json:
        pr = event_json['pull_request']

        if 'number' in pr:
            return int(pr['number'])

    # Not a PR
    return 0


# Read github event data
def read_event():
    # Find path
    event_path = get_env_var('GITHUB_EVENT_PATH')

    # Read json contents
    with open(event_path, 'r') as f:
        json_data = json.load(f)

    return json_data


# Look up env var
def get_env_var(env_var_name, strict=True):
    # Check env var
    value = os.getenv(env_var_name)

    # Handle missing value
    if not value:
        if strict:
            if env_var_name == 'GITHUB_TOKEN':
                print(f'error: env var not found: {env_var_name}')
                print('''please ensure your workflow step includes
                env:
                    GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}''')
                sys.exit(1)

            else:
                print(f'error: env var not found: {env_var_name}')
                sys.exit(1)

    return value


# Handle interrupt
def signal_handler(_, __):
    print(' ')
    sys.exit(0)


####
# MAIN
####

# Set up Ctrl-C handler
signal.signal(signal.SIGINT, signal_handler)

# Invoke main method
if __name__ == '__main__':
    main()


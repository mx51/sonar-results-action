# Sonar Results Github Action


## Overview

This Github Action retrieves SonarQube scan results from a nominated project and creates a comment in the current Pull Request displaying those results.


## Requirements


### Environment

The following environment variables are required to run this Github Action:

```
GITHUB_TOKEN    # Can be sourced using ${{ secrets.GITHUB_TOKEN }}
SONAR_TOKEN     # Sonarqube access token for retrieving results
SONAR_HOST_URL  # URL of your Sonarqube service
```


### Github Action Workflow

Since this action is designed to update Github Pull Requests, it is recommended to use the following workflow trigger configuration:

```
on:
  pull_request:
    types: [ opened, synchronize, reopened, edited ]
...

```

This ensures the latest SonarQube scan results, when used in conjunction with the [SonarQube Scan Github Action](https://github.com/SonarSource/sonarqube-scan-action), are presented on the pull request whenever code changes are made.


### Example Action

```
    - name: Display Quality Report
      uses: mx51/sonar-results-action@master
      env:
        GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        SONAR_TOKEN: ${{ secrets.SONAR_TOKEN }}
        SONAR_HOST_URL: ${{ secrets.SONAR_HOST_URL }}
```


## Notes

- a single pull request comment is created on each pull request that uses this action
- the pull request comment is updated each time a code change is made to the pull request branch


## References

- https://docs.github.com/en/actions/creating-actions/creating-a-composite-action
- https://medium.com/intelligentmachines/github-actions-building-and-publishing-own-actions-using-python-d94e2724b08c


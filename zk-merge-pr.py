#!/usr/bin/env python

#
# Licensed to the Apache Software Foundation (ASF) under one or more
# contributor license agreements.  See the NOTICE file distributed with
# this work for additional information regarding copyright ownership.
# The ASF licenses this file to You under the Apache License, Version 2.0
# (the "License"); you may not use this file except in compliance with
# the License.  You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

# Utility for creating well-formed pull request merges and pushing them to Apache. This script is a modified version
# of the one created by the Spark project (https://github.com/apache/spark/blob/master/dev/merge_spark_pr.py).
#
# Usage: ./zk-merge-pr.py (see config env vars below)
#
# This utility assumes you already have a local ZooKeeper git folder and that you
# have added remotes corresponding to both:
# (i) the github apache ZooKeeper mirror and
# (ii) the apache ZooKeeper git repo.

import json
import os
import re
import subprocess
import sys
import urllib.request, urllib.error, urllib.parse
import getpass
import requests

try:
    import jira.client
    JIRA_IMPORTED = True
except ImportError:
    JIRA_IMPORTED = False

PROJECT_NAME = "zookeeper"

CAPITALIZED_PROJECT_NAME = PROJECT_NAME.upper()

# Remote name which points to the GitHub site
PR_REMOTE_NAME = os.environ.get("PR_REMOTE_NAME", "apache-github")
# Remote name which points to Apache git
PUSH_REMOTE_NAME = os.environ.get("PUSH_REMOTE_NAME", "apache")
# ASF JIRA username
JIRA_USERNAME = os.environ.get("JIRA_USERNAME", "")
# ASF JIRA password
JIRA_PASSWORD = os.environ.get("JIRA_PASSWORD", "")
# OAuth key used for issuing requests against the GitHub API. If this is not defined, then requests
# will be unauthenticated. You should only need to configure this if you find yourself regularly
# exceeding your IP's unauthenticated request rate limit. You can create an OAuth key at
# https://github.com/settings/tokens. This script only requires the "public_repo" scope.
GITHUB_OAUTH_KEY = os.environ.get("GITHUB_OAUTH_KEY")

GITHUB_USER = os.environ.get("GITHUB_USER", "apache")
GITHUB_BASE = "https://github.com/%s/%s/pull" % (GITHUB_USER, PROJECT_NAME)
GITHUB_API_BASE = "https://api.github.com/repos/%s/%s" % (GITHUB_USER, PROJECT_NAME)
JIRA_BASE = "https://issues.apache.org/jira/browse"
JIRA_API_BASE = "https://issues.apache.org/jira"
# Prefix added to temporary branches
TEMP_BRANCH_PREFIX = "PR_TOOL"
# TODO Introduce a convention as this is too brittle
RELEASE_BRANCH_PREFIX = "branch-"

DEV_BRANCH_NAME = "master"

DEFAULT_FIX_VERSION = os.environ.get("DEFAULT_FIX_VERSION", "branch-3.5")

def get_json(url):
    try:
        request = urllib.request.Request(url)
        if GITHUB_OAUTH_KEY:
            request.add_header('Authorization', 'token %s' % GITHUB_OAUTH_KEY)
        return json.load(urllib.request.urlopen(request))
    except urllib.error.HTTPError as e:
        if "X-RateLimit-Remaining" in e.headers and e.headers["X-RateLimit-Remaining"] == '0':
            print("Exceeded the GitHub API rate limit; see the instructions in " + \
                  "zk-merge-pr.py to configure an OAuth token for making authenticated " + \
                  "GitHub requests.")
        else:
            print("Unable to fetch URL, exiting: %s" % url)
        sys.exit(-1)


def fail(msg):
    print(msg)
    clean_up()
    sys.exit(-1)


def run_cmd(cmd):
    print(cmd)
    if isinstance(cmd, list):
        return subprocess.check_output(cmd, encoding='utf8')
    else:
        return subprocess.check_output(cmd.split(" "), encoding='utf8')


def continue_maybe(prompt):
    result = input("\n%s (y/n): " % prompt)
    if result.lower().strip() != "y":
        fail("Okay, exiting")

def clean_up():
    if original_head != get_current_branch():
        print("Restoring head pointer to %s" % original_head)
        run_cmd("git checkout %s" % original_head)

    branches = run_cmd("git branch").replace(" ", "").split("\n")

    for branch in [x for x in branches if x.startswith(TEMP_BRANCH_PREFIX)]:
        print("Deleting local branch %s" % branch)
        run_cmd("git branch -D %s" % branch)

def get_current_branch():
    return run_cmd("git rev-parse --abbrev-ref HEAD").replace("\n", "")

# merge the requested PR and return the merge hash
def merge_pr(pr_num, title, pr_repo_desc):

    # Retrieve the commits separately.
    json_commits = get_json(f"https://api.github.com/repos/{PUSH_REMOTE_NAME}/{PROJECT_NAME}/pulls/{pr_num}/commits")
    merge_message = []
    if json_commits and isinstance(json_commits, list):
        for commit in json_commits:
            commit_message = commit['commit']['message']
            merge_message += [commit_message]

    # Check for disapproval reviews.
    json_reviewers = get_json(f"https://api.github.com/repos/{PUSH_REMOTE_NAME}/{PROJECT_NAME}/pulls/{pr_num}/reviews")
    disapproval_reviews = [review['user']['login'] for review in json_reviewers if review['state'] == 'CHANGES_REQUESTED']
    if disapproval_reviews:
        continue_maybe("Warning: There are requested changes. Proceed with merging pull request #%s?" % pr_num)
    # Verify if there are no approved reviews.
    approved_reviewers = [review['user']['login'] for review in json_reviewers if review['state'] == 'APPROVED']
    if not approved_reviewers:
        continue_maybe("Warning: Pull Request does not have an approved review. Proceed with merging pull request #%s?" % pr_num)
    else:
        reviewers_string = ', '.join(approved_reviewers)
        merge_message += [f"Reviewers: {reviewers_string}"]
    # Check the author and the closing line.
    json_pr = get_json(f"https://api.github.com/repos/{PUSH_REMOTE_NAME}/{PROJECT_NAME}/pulls/{pr_num}")
    primary_author = json_pr["user"]["login"]
    if primary_author != "":
        merge_message += [f"Author: {primary_author}"]
    close_line = "Closes #%s from %s" % (pr_num, pr_repo_desc)
    merge_message += [close_line]
    merged_string = '\n'.join(merge_message)

    # Get the latest commit SHA.
    latest_commit_sha = json_pr["head"]["sha"]
    json_status = get_json(f"https://api.github.com/repos/{PUSH_REMOTE_NAME}/{PROJECT_NAME}/commits/{latest_commit_sha}/check-runs")
    # Check if all checks have passed on GitHub.
    all_checks_passed = all(status["conclusion"] == "success" for status in json_status["check_runs"])
    if all_checks_passed:
        print("All checks have passed on the github.")
    else:
        any_in_progress = any(run["status"] == "in_progress" for run in json_status["check_runs"])
        if any_in_progress:
            continue_maybe("Warning: There are pending checks. Would you like to continue the merge?")
        else:
            continue_maybe("Warning: Not all checks have passed on GitHub. Would you like to continue the merge?")

    headers = {
        "Authorization": f"token {GITHUB_OAUTH_KEY}",
        "Accept": "application/vnd.github.v3+json"
    }
    data = {
        "commit_title": title,
        "commit_message": merged_string,
        "merge_method": "squash"
    }

    response = requests.put(f"https://api.github.com/repos/{PUSH_REMOTE_NAME}/{PROJECT_NAME}/pulls/{pr_num}/merge", headers=headers, json=data)

    if response.status_code == 200:
        merge_response_json = response.json()
        merge_commit_sha = merge_response_json.get("sha")
        print(f"Pull request #{pr_num} merged. Sha: #{merge_commit_sha}")
        return merge_commit_sha
    else:
        print(f"Failed to merge pull request #{pr_num}. Status code: {response.status_code}")
        print(response.text)
        exit()

def cherry_pick(pr_num, merge_hash, default_branch):
    pick_ref = input("Enter a branch name [%s]: " % default_branch)
    if pick_ref == "":
        pick_ref = default_branch

    pick_branch_name = "%s_PICK_PR_%s_%s" % (TEMP_BRANCH_PREFIX, pr_num, pick_ref.upper())

    run_cmd("git fetch %s" % PUSH_REMOTE_NAME)
    run_cmd("git checkout -b %s %s/%s" % (pick_branch_name, PUSH_REMOTE_NAME, pick_ref))

    try:
        run_cmd("git cherry-pick -sx %s" % merge_hash)
    except Exception as e:
        msg = "Error cherry-picking: %s\nWould you like to manually fix-up this merge?" % e
        continue_maybe(msg)
        msg = "Okay, please fix any conflicts and finish the cherry-pick. Finished?"
        continue_maybe(msg)

    continue_maybe("Pick complete (local ref %s). Push to %s?" % (
        pick_branch_name, PUSH_REMOTE_NAME))

    try:
        run_cmd('git push %s %s:%s' % (PUSH_REMOTE_NAME, pick_branch_name, pick_ref))
    except Exception as e:
        clean_up()
        fail("Exception while pushing: %s" % e)

    pick_hash = run_cmd("git rev-parse %s" % pick_branch_name)[:8]
    clean_up()

    print(("Pull request #%s picked into %s!" % (pr_num, pick_ref)))
    print(("Pick hash: %s" % pick_hash))
    return pick_ref


def fix_version_from_branch(branch, versions):
    # Note: Assumes this is a sorted (newest->oldest) list of un-released versions
    if branch == DEV_BRANCH_NAME:
        versions = [x for x in versions if x == DEFAULT_FIX_VERSION]
        if len(versions) > 0:
            return versions[0]
        else:
            return None
    else:
        versions = [x for x in versions if x.startswith(branch)]
        if len(versions) > 0:
            return versions[-1]
        else:
            return None


def resolve_jira_issue(merge_branches, comment, default_jira_id=""):
    asf_jira = jira.client.JIRA({'server': JIRA_API_BASE},
                                basic_auth=(JIRA_USERNAME, JIRA_PASSWORD))

    jira_id = input("Enter a JIRA id [%s]: " % default_jira_id)
    if jira_id == "":
        jira_id = default_jira_id

    try:
        issue = asf_jira.issue(jira_id)
    except Exception as e:
        fail("ASF JIRA could not find %s\n%s" % (jira_id, e))

    cur_status = issue.fields.status.name
    cur_summary = issue.fields.summary
    cur_assignee = issue.fields.assignee
    if cur_assignee is None:
        cur_assignee = "NOT ASSIGNED!!!"
    else:
        cur_assignee = cur_assignee.displayName

    if cur_status == "Resolved" or cur_status == "Closed":
        fail("JIRA issue %s already has status '%s'" % (jira_id, cur_status))
    print(("=== JIRA %s ===" % jira_id))
    print(("summary\t\t%s\nassignee\t%s\nstatus\t\t%s\nurl\t\t%s/%s\n" % (
        cur_summary, cur_assignee, cur_status, JIRA_BASE, jira_id)))

    versions = asf_jira.project_versions(CAPITALIZED_PROJECT_NAME)
    versions = sorted(versions, key=lambda x: x.name, reverse=True)
    versions = [x for x in versions if x.raw['released'] is False]

    version_names = [x.name for x in versions]
    default_fix_versions = [fix_version_from_branch(x, version_names) for x in merge_branches]
    default_fix_versions = [x for x in default_fix_versions if x != None]
    default_fix_versions = ",".join(default_fix_versions)

    fix_versions = input("Enter comma-separated fix version(s) [%s]: " % default_fix_versions)
    if fix_versions == "":
        fix_versions = default_fix_versions
    fix_versions = fix_versions.replace(" ", "").split(",")

    def get_version_json(version_str):
        return [v for v in versions if v.name == version_str][0].raw

    jira_fix_versions = [get_version_json(v) for v in fix_versions]

    resolve = [a for a in asf_jira.transitions(jira_id) if a['name'] == "Resolve Issue"][0]
    resolution = [r for r in asf_jira.resolutions() if r.raw['name'] == "Fixed"][0]
    asf_jira.transition_issue(
        jira_id, resolve["id"], fixVersions = jira_fix_versions,
        comment = comment, resolution = {'id': resolution.raw['id']})

    print("Successfully resolved %s with fixVersions=%s!" % (jira_id, fix_versions))


def resolve_jira_issues(title, merge_branches, comment):
    jira_ids = re.findall("%s-[0-9]+" % CAPITALIZED_PROJECT_NAME, title)

    if len(jira_ids) == 0:
        resolve_jira_issue(merge_branches, comment)
    for jira_id in jira_ids:
        resolve_jira_issue(merge_branches, comment, jira_id)


def standardize_jira_ref(text):
    """
    Standardize the jira reference commit message prefix to "PROJECT_NAME-XXX: Issue"

    >>> standardize_jira_ref("%s-5954: Top by key" % CAPITALIZED_PROJECT_NAME)
    'ZOOKEEPER-5954: Top by key'
    >>> standardize_jira_ref("%s-5821: ParquetRelation2 CTAS should check if delete is successful" % PROJECT_NAME)
    'ZOOKEEPER-5821: ParquetRelation2 CTAS should check if delete is successful'
    >>> standardize_jira_ref("%s-4123: [WIP] Show new dependencies added in pull requests" % PROJECT_NAME)
    'ZOOKEEPER-4123: [WIP] Show new dependencies added in pull requests'
    >>> standardize_jira_ref("%s  5954: Top by key" % PROJECT_NAME)
    'ZOOKEEPER-5954: Top by key'
    >>> standardize_jira_ref("%s-979: a LRU scheduler for load balancing in TaskSchedulerImpl" % PROJECT_NAME)
    'ZOOKEEPER-979: a LRU scheduler for load balancing in TaskSchedulerImpl'
    >>> standardize_jira_ref("%s-1094: Support MiMa for reporting binary compatibility across versions." % CAPITALIZED_PROJECT_NAME)
    'ZOOKEEPER-1094: Support MiMa for reporting binary compatibility across versions.'
    >>> standardize_jira_ref("%s-1146: [WIP] Vagrant support" % CAPITALIZED_PROJECT_NAME)
    'ZOOKEEPER-1146: [WIP] Vagrant support'
    >>> standardize_jira_ref("%s-1032: If Yarn app fails before registering, app master stays aroun..." % PROJECT_NAME)
    'ZOOKEEPER-1032: If Yarn app fails before registering, app master stays aroun...'
    >>> standardize_jira_ref("%s-6250 %s-6146 %s-5911: Types are now reserved words in DDL parser." % (PROJECT_NAME, PROJECT_NAME, CAPITALIZED_PROJECT_NAME))
    'ZOOKEEPER-6250 ZOOKEEPER-6146 ZOOKEEPER-5911: Types are now reserved words in DDL parser.'
    >>> standardize_jira_ref("Additional information for users building from source code")
    'Additional information for users building from source code'
    """
    jira_refs = []
    components = []

    # Extract JIRA ref(s):
    pattern = re.compile(r'(%s[-\s]*[0-9]{3,6})+' % CAPITALIZED_PROJECT_NAME, re.IGNORECASE)
    for ref in pattern.findall(text):
        # Add brackets, replace spaces with a dash, & convert to uppercase
        jira_refs.append(re.sub(r'\s+', '-', ref.upper()))
        text = text.replace(ref, '')

    # Extract project name component(s):
    # Look for alphanumeric chars, spaces, dashes, periods, and/or commas
    pattern = re.compile(r'(\[[\w\s,-\.]+\])', re.IGNORECASE)
    for component in pattern.findall(text):
        components.append(component.upper())
        text = text.replace(component, '')

    # Cleanup any remaining symbols:
    pattern = re.compile(r'^\W+(.*)', re.IGNORECASE)
    if (pattern.search(text) is not None):
        text = pattern.search(text).groups()[0]

    # Assemble full text (JIRA ref(s), module(s), remaining text)
    jira_prefix = ' '.join(jira_refs).strip()
    if jira_prefix:
        jira_prefix = jira_prefix + ": "
    clean_text = jira_prefix + ' '.join(components).strip() + " " + text.strip()

    # Replace multiple spaces with a single space, e.g. if no jira refs and/or components were included
    clean_text = re.sub(r'\s+', ' ', clean_text.strip())

    return clean_text

def get_remote_repos():
    repos = run_cmd("git remote -v").split()

    dict = {}
    for i in range(0, len(repos), 3):
        dict[repos[i]] = repos[i+1]
    return dict


def check_git_remote():
    repos = get_remote_repos()

    # check if all remote endpoints' URLs point to project git repo
    name = PROJECT_NAME + ".git"
    for url in list(repos.values()):
        if not url.endswith(name):
            fail("Error: not a %s git repo or at least one remote is invalid" % PROJECT_NAME)

    if not PR_REMOTE_NAME in repos:
        fail("Error: PR_REMOTE_NAME (%s) environment variable has not been set!" % PR_REMOTE_NAME)

    if not PUSH_REMOTE_NAME in repos:
        fail("Error: PUSH_REMOTE_NAME (%s) environment variable has not been set!" % PUSH_REMOTE_NAME)


def check_jira_env():

    global JIRA_PASSWORD

    if JIRA_IMPORTED:

       if JIRA_USERNAME.strip() != "" and JIRA_PASSWORD.strip() == "":
           inform_pwd = input("JIRA_USERNAME set but JIRA_PASSWORD is not. Want to inform it? ")
           if inform_pwd.strip() == "y":
               JIRA_PASSWORD = getpass.getpass('JIRA PASSWORD: ')

       if JIRA_USERNAME.strip() == "" or JIRA_PASSWORD.strip() == "":
           msg ="JIRA_USERNAME and/or JIRA_PASSWORD are not set. Want to continue? "
           continue_maybe(msg)
    else:
        msg = "JIRA lib not installed. Want to continue? "
        continue_maybe(msg)

def main():
    global original_head

    original_head = get_current_branch()

    check_jira_env()

    check_git_remote()

    branches = get_json("%s/branches" % GITHUB_API_BASE)
    branch_names = [x for x in [x['name'] for x in branches] if x.startswith(RELEASE_BRANCH_PREFIX)]
    # Assumes branch names can be sorted lexicographically
    latest_branch = sorted(branch_names, reverse=True)[0]

    pr_num = input("Which pull request would you like to merge? (e.g. 34): ")
    pr = get_json("%s/pulls/%s" % (GITHUB_API_BASE, pr_num))

    # Check if the pull request has already been closed or merged.
    pull_request_state = pr.get("state", "")
    if pull_request_state == "closed":
        merge_hash = pr.get("merge_commit_sha", "")
        merged = pr.get("merged")
        # Verify if the pull request has been merged by the GitHub API.
        if merged is True:
            print(f"Pull request #{pr['number']} has already been merged, assuming you want to backport")
            cherry_pick(pr_num, merge_hash, latest_branch)
            sys.exit(0)
        # Some merged pull requests may not appear as merged in the GitHub API,
        # for example, those closed by an older version of this script.
        else:
            pr_events = get_json("%s/issues/%s/events" % (GITHUB_API_BASE, pr_num))
            for event in pr_events:
                if event.get("event") == "closed":
                    commit_id = event.get("commit_id")
                    if commit_id is not None:
                        print(f"Pull request #{pr['number']} has already been merged, assuming you want to backport")
                        cherry_pick(pr_num, merge_hash, latest_branch)
                        sys.exit(0)
                    else:
                        print(f"Pull request #{pr['number']} has already been closed, but not merged, exiting.")
                        exit()

    if not bool(pr["mergeable"]):
        print(f"Pull request %s is not mergeable in its current form.\n" % pr_num)
        exit()

    url = pr["url"]

    pr_title = pr["title"]
    commit_title = input("Commit title [%s]: " % pr_title)
    if commit_title == "":
        commit_title = pr_title

    # Decide whether to use the modified title or not
    modified_title = standardize_jira_ref(commit_title)
    if modified_title != commit_title:
        print("I've re-written the title as follows to match the standard format:")
        print("Original: %s" % commit_title)
        print("Modified: %s" % modified_title)
        result = input("Would you like to use the modified title? (y/n): ")
        if result.lower().strip() == "y":
            commit_title = modified_title
            print("Using modified title:")
        else:
            print("Using original title:")
        print(commit_title)

    target_ref = pr["base"]["ref"]
    user_login = pr["user"]["login"]
    base_ref = pr["head"]["ref"]
    pr_repo_desc = "%s/%s" % (user_login, base_ref)

    print(("\n=== Pull Request #%s ===" % pr_num))
    print(("PR title\t%s\nCommit title\t%s\nSource\t\t%s\nTarget\t\t%s\nURL\t\t%s" % (
        pr_title, commit_title, pr_repo_desc, target_ref, url)))
    continue_maybe("Proceed with merging pull request #%s?" % pr_num)

    merged_refs = [target_ref]

    merge_hash = merge_pr(pr_num, commit_title, pr_repo_desc)

    pick_prompt = "Would you like to pick %s into another branch?" % merge_hash
    while input("\n%s (y/n): " % pick_prompt).lower().strip() == "y":
        merged_refs = merged_refs + [cherry_pick(pr_num, merge_hash, latest_branch)]

    if JIRA_IMPORTED:
        if JIRA_USERNAME and JIRA_PASSWORD:
            continue_maybe("Would you like to update an associated JIRA?")
            jira_comment = "Issue resolved by pull request %s\n[%s/%s]" % (pr_num, GITHUB_BASE, pr_num)
            resolve_jira_issues(commit_title, merged_refs, jira_comment)
        else:
            print("JIRA_USERNAME and JIRA_PASSWORD not set")
            print("Exiting without trying to close the associated JIRA.")
    else:
        print("Could not find jira-python library. Run 'sudo pip install jira' to install.")
        print("Exiting without trying to close the associated JIRA.")

if __name__ == "__main__":
    import doctest
    (failure_count, test_count) = doctest.testmod()
    if (failure_count):
        exit(-1)

    main()

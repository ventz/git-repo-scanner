import os
from flask import Flask, request, render_template
from nightfall import Confidence, DetectionRule, Detector, RedactionConfig, MaskConfig, Nightfall
from datetime import datetime, timedelta
import urllib.request, urllib.parse, json
import csv
import requests

app = Flask(__name__)

nightfall = Nightfall(
	key=os.getenv('NIGHTFALL_API_KEY'),
	signing_secret=os.getenv('NIGHTFALL_SIGNING_SECRET')
)

# create CSV where sensitive findings will be written
headers = ["upload_id", "#", "datetime", "org", "repo", "filepath", "before_context", "finding", "after_context", "detector", "confidence", "line", "detection_rules", "commit_hash", "commit_date", "author_email", "permalink"]
with open(f"results.csv", 'a') as csvfile:
	writer = csv.writer(csvfile)
	writer.writerow(headers)

# respond to POST requests at /ingest
# Nightfall will send requests to this webhook endpoint with file scan results
@app.route("/ingest", methods=['POST'])
def ingest():
	data = request.get_json(silent=True)
	# validate webhook URL with challenge response
	challenge = data.get("challenge") 
	if challenge:
		return challenge
	# challenge was passed, now validate the webhook payload
	else: 
		# get details of the inbound webhook request for validation
		request_signature = request.headers.get('X-Nightfall-Signature')
		request_timestamp = request.headers.get('X-Nightfall-Timestamp')
		request_data = request.get_data(as_text=True)

		if nightfall.validate_webhook(request_signature, request_timestamp, request_data):
			# check if any sensitive findings were found in the file, return if not
			if not data["findingsPresent"]: 
				print("No sensitive data present!")
				return "", 200

			# there are sensitive findings in the file
			output_results(data)
			return "", 200
		else:
			return "Invalid webhook", 500

# get hostname for GitHub API calls depending on cloud vs enterprise
def get_hostname():
	if os.getenv('GITHUB_HOSTNAME') and os.getenv('GITHUB_HOSTNAME') != "github.com":
		return f"{os.getenv('GITHUB_HOSTNAME')}/api/v3"
	return "api.github.com"

# get permalink to the line of the finding in the specific GitHub commit
def get_permalink(url, finding):
	path = finding['path'].split("/")
	if len(path) > 1:
		path.pop(0)
	path = "/".join(path)
	path = path.split(":")
	path = path[0]
	# print(path)
	return path, f"{url}/blob/{finding['location']['commitHash']}/{path}#L{finding['location']['lineRange']['start']}"

# get details of the commit from GitHub
def get_commit(org, repo, commit_hash):
	headers = {
	    'Authorization': f"token {os.getenv('GITHUB_PERSONAL_ACCESS_TOKEN')}",
	    'Accept': 'application/vnd.github.v3+json'
	}

	response = requests.get(f"https://{get_hostname()}/repos/{org}/{repo}/commits/{commit_hash}", headers=headers)
	commit = json.loads(response.content)
	return commit['commit']['author']

# output findings to CSV
def output_results(data):
	findings_url = data['findingsURL']
	# open findings URL provided by Nightfall to access findings
	with urllib.request.urlopen(findings_url) as url:
		findings = json.loads(url.read().decode())
		findings = findings['findings']

	filepath, url, org, repo = "", "", "", ""

	if 'requestMetadata' in data:
		metadata = data['requestMetadata']
		metadata = json.loads(metadata)
		filepath = metadata['filepath']
		url = metadata['url']
		org = metadata['org_name']
		repo = metadata['repo_name']

	print(f"Sensitive data found in {filepath} | Outputting {len(findings)} finding(s) to CSV | UploadID {data['uploadID']}")
	table = []
	# loop through findings JSON, get relevant finding metadata, write each finding as a row into output CSV
	for i, finding in enumerate(findings):
		before_context = ""
		if 'beforeContext' in finding:
			before_context = repr(finding['beforeContext'])
		after_context = ""
		if 'afterContext' in finding:
			after_context = repr(finding['afterContext'])
		
		filepath, permalink = get_permalink(url, finding)
		commit_author = get_commit(org, repo, finding['location']['commitHash'])

		row = [
			data['uploadID'],
			i+1,
			datetime.now(),
			org,
			repo,
			filepath,
			before_context, 
			repr(finding['finding']),
			after_context,
			finding['detector']['name'],
			finding['confidence'],
			finding['location']['lineRange']['start'],
			finding['matchedDetectionRuleUUIDs'],
			finding['location']['commitHash'],
			commit_author['date'],
			commit_author['email'],
			permalink
		]
		table.append(row)
		with open(f"results.csv", 'a') as csvfile:
			writer = csv.writer(csvfile)
			writer.writerow(row)
	return

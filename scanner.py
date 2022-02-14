import os
from nightfall import Confidence, DetectionRule, Detector, RedactionConfig, MaskConfig, Nightfall
from os import walk
import requests
import json
from git import Repo
import shutil

# get hostname for GitHub API calls depending on cloud vs enterprise
def get_hostname():
	if os.getenv('GITHUB_HOSTNAME') and os.getenv('GITHUB_HOSTNAME') != "github.com":
		return f"{os.getenv('GITHUB_HOSTNAME')}/api/v3"
	return "api.github.com"

# download GitHub repo as local zip archive
def download_repo(dir, org_name, repo_name):
	repo = f"{org_name}/{repo_name}"
	git_url = f"https://{os.getenv('GITHUB_USERNAME')}:{os.getenv('GITHUB_PERSONAL_ACCESS_TOKEN')}@{os.getenv('GITHUB_HOSTNAME')}/{repo}.git"	
	repo_dir = f"{dir}/{org_name}--{repo_name}"

	try:
		os.mkdir(repo_dir)
	except:
		pass

	try:
		Repo.clone_from(git_url, repo_dir)
		shutil.make_archive(repo_dir, 'zip', repo_dir)
		shutil.rmtree(repo_dir)
		return f"{repo_dir}.zip"
	except Exception as e:
		print(f"Error downloading repo {git_url}", e)
		return False

# iterate through all GitHub orgs and repos within them, download each repo and scan with Nightfall
def download_all_repos(dir):
	headers = {
	    'Authorization': f"token {os.getenv('GITHUB_PERSONAL_ACCESS_TOKEN')}",
	    'Accept': 'application/vnd.github.v3+json'
	}

	hostname = get_hostname()
	orgs_endpoint = f"https://{hostname}/organizations"
	if hostname == "api.github.com":
		orgs_endpoint = f"https://{hostname}/user/memberships/orgs"

	response = requests.get(orgs_endpoint, headers=headers)
	orgs = json.loads(response.content)
	
	if hostname == "api.github.com":
		orgs = [ org['organization'] for org in orgs ]
	
	try:
		os.mkdir(dir)
	except:
		pass

	for org in orgs:
		print(f"Organization: {org['login']}")
		response = requests.get(f"https://{hostname}/orgs/{org['login']}/repos", headers=headers)
		repos = json.loads(response.content)
		for i, repo in enumerate(repos):
			# print(org, repo)
			save_path = download_repo(dir, org['login'], repo['name'])
			if save_path:
				scan_repo(save_path, repo['html_url'], org['login'], repo['name'])

# send zip archive of GitHub repo to Nightfall to be scanned
def scan_repo(filepath, url, org, repo):
	nightfall = Nightfall() # reads API key from NIGHTFALL_API_KEY environment variable by default
	webhook_url = f"{os.getenv('NIGHTFALL_SERVER_URL')}/ingest"
	detection_rule_uuids = os.getenv('NIGHTFALL_DETECTION_RULE_UUIDS')
	detection_rule_uuids = [ str.strip() for str in detection_rule_uuids.split(",") ]

	try:
		print(f"\tScanning {url}")
		metadata = { "filepath": filepath, "url": url, "org_name": org, "repo_name": repo }
		metadata = json.dumps(metadata)
		# scan with Nightfall
		scan_id, message = nightfall.scan_file(filepath, 
			webhook_url=webhook_url,
			detection_rule_uuids=detection_rule_uuids, 
			request_metadata=metadata)
		print("\t\t", scan_id, message)
	except Exception as err:
		print(err)

# clean up all downloaded GitHub repos
def delete_all_repos(dir):
	print("Cleaning up")
	shutil.rmtree(dir)

dir = 'repos-temp'
download_all_repos(dir)
delete_all_repos(dir)
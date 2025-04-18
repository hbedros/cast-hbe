import requests
from typing import Dict, Optional, List
import logging
from requests.adapters import HTTPAdapter
import json
import subprocess
import sys
import os
import zipfile
from urllib.parse import urlparse
import shutil
import time


class RepoDetails:
    def __init__(self, repo_url: str, assessed_branch: str, transformed_branch: str):
        self.repo_url = repo_url
        self.assessed_branch = assessed_branch
        self.transformed_branch = transformed_branch
        self.assessed_branch_folder = ""    # Will store the path where assessed branch is downloaded
        self.transformed_branch_folder = "" # Will store the path where transformed branch is downloaded
        
    def __str__(self) -> str:
        return (f"RepoDetails(repo_url={self.repo_url}, "
                f"assessed_branch={self.assessed_branch}, "
                f"transformed_branch={self.transformed_branch}, "
                f"assessed_folder={self.assessed_branch_folder}, "
                f"transformed_folder={self.transformed_branch_folder})")

class JsonReader:
    def __init__(self, json_data: str):
        self.data = json.loads(json_data)
        self.target_branch = self._get_target_branch()
        
    def _get_target_branch(self) -> str:
        return self.data.get("jobDetail", {}).get("targetBranch", "")

    def get_repo_details(self) -> List[RepoDetails]:
        repo_details_list = []
        repositories = self.data.get("repositories", [])
        for repo in repositories:
            repo_location = repo.get("repositoryLocation", {})
            repo_url = repo_location.get("url", "")
            source_branch = repo.get("sourceBranch", "")
            
            repo_details = RepoDetails(
                repo_url=repo_url,
                assessed_branch=source_branch,
                transformed_branch=self.target_branch
            )
            repo_details_list.append(repo_details)
        return repo_details_list

class GithubRepoDownloader:
    def __init__(self, token: str):
        self.token = token
        self.headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json"
        }

    def download_repo(self, repo_url: str, branch: str, output_folder: str) -> Optional[str]:
        path_parts = urlparse(repo_url).path.strip('/').split('/')
        if len(path_parts) < 2:
            logging.error("Invalid GitHub URL")
            return None

        owner, repo = path_parts[:2]
        api_url = f"https://api.github.com/repos/{owner}/{repo}/zipball/{branch}"

        try:
            os.makedirs(output_folder, exist_ok=True)
            
            response = requests.get(api_url, headers=self.headers, stream=True)
            response.raise_for_status()

            zip_path = os.path.join(output_folder, f"{repo}-{branch}.zip")
            with open(zip_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)

            final_folder = os.path.join(output_folder, f"{repo}-{branch}")
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(output_folder)

            os.remove(zip_path)
            extracted_folder = os.path.join(output_folder, os.listdir(output_folder)[0])
            if os.path.exists(final_folder):
                import shutil
                shutil.rmtree(final_folder)
            os.rename(extracted_folder, final_folder)

            logging.info(f"Repository downloaded and extracted to {final_folder}")
            return final_folder

        except Exception as e:
            logging.error(f"Error downloading repository: {str(e)}")
            return None

class CastApiClient:
    def __init__(self, auth_token: str, timeout: int = 30):
        self.base_url = "https://rpa.casthighlight.com/WS2".rstrip('/')
        self.session = self._create_session()
        self.timeout = timeout
        self.auth_token = auth_token
        self.headers = {
            'Authorization': f"Bearer {auth_token}",
            'Content-Type': 'application/json'
        }

    def _create_session(self) -> requests.Session:
        session = requests.Session()
        adapter = HTTPAdapter(max_retries=3)
        session.mount('http://', adapter)
        session.mount('https://', adapter)
        return session

    def execute_analysis(self, work_dir: str, src_dir: str, date_time: int, snapshot_label: str = "test") -> int:
        print(f"\n{'='*80}")
        print(f"Starting analysis:")
        print(f"Working directory: {work_dir}")
        print(f"Source directory: {src_dir}")
        print(f"{'='*80}\n")
        
        if not os.path.exists(work_dir):
            logging.error(f"Working directory does not exist: {work_dir}")
            return 1
            
        if not os.path.exists(src_dir):
            logging.error(f"Source directory does not exist: {src_dir}")
            return 1

        cast_tool_dir = "/Users/rakskuma/cast_tool/Highlight-Automation-Command"
        if not os.path.exists(cast_tool_dir):
            logging.error(f"CAST tool directory does not exist: {cast_tool_dir}")
            return 1

        original_dir = os.getcwd()
        try:
            os.chdir(cast_tool_dir)
            
            command = [
                "java", "-jar", "HighlightAutomation.jar",
                "--allowGeneratedCode",
                "--workingDir", work_dir,
                "--sourceDir", src_dir,
                "--companyId", "33168",
                "--applicationId", "480216",
                "--keywordScan", "/Users/rakskuma/Downloads/cast.keyword.dotnet.1.0.0.xml",
                "--serverUrl", "https://rpa.casthighlight.com/",
                "--tokenAuth", self.auth_token,
                "--snapshotDatetime",  date_time,
                "--snapshotLabel", snapshot_label       
                ]

            print("Executing command:")
            print(f"cd {cast_tool_dir} && {' '.join(command)}\n")

            # Run the command and capture output in real-time
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                universal_newlines=True
            )

            # Print output in real-time
            print("Command output:")
            print("-" * 80)
            
            stdout_lines = []
            stderr_lines = []
            
            while True:
                # Read stdout
                stdout_line = process.stdout.readline()
                if stdout_line:
                    print(f"[STDOUT] {stdout_line.rstrip()}")
                    stdout_lines.append(stdout_line)
                
                # Read stderr
                stderr_line = process.stderr.readline()
                if stderr_line:
                    print(f"[STDERR] {stderr_line.rstrip()}", file=sys.stderr)
                    stderr_lines.append(stderr_line)
                
                # Check if process has finished
                if process.poll() is not None:
                    # Get remaining output
                    remaining_stdout, remaining_stderr = process.communicate()
                    if remaining_stdout:
                        print(f"[STDOUT] {remaining_stdout.rstrip()}")
                        stdout_lines.append(remaining_stdout)
                    if remaining_stderr:
                        print(f"[STDERR] {remaining_stderr.rstrip()}", file=sys.stderr)
                        stderr_lines.append(remaining_stderr)
                    break
            
            print("-" * 80)
            
            # Log complete output
            if stdout_lines:
                logging.info("Complete stdout output:\n%s", "".join(stdout_lines))
            if stderr_lines:
                logging.warning("Complete stderr output:\n%s", "".join(stderr_lines))
            
            return_code = process.returncode
            print(f"\nCommand completed with return code: {return_code}")
            
            return return_code

        except Exception as e:
            logging.error("Unexpected error during analysis: %s", str(e))
            print(f"Error during analysis: {str(e)}")
            return 1
        finally:
            os.chdir(original_dir)

def process_repositories(json_file_path: str, github_token: str, cast_token: str):
    base_output_dir = "/tmp/output"
    shutil.rmtree(base_output_dir)
    os.makedirs(base_output_dir, exist_ok=True)

    with open(json_file_path, 'r') as f:
        json_data = f.read()
    
    json_reader = JsonReader(json_data)
    repo_details_list = json_reader.get_repo_details()
    
    downloader = GithubRepoDownloader(github_token)
    cast_client = CastApiClient(auth_token=cast_token)
    
    for i, repo_details in enumerate(repo_details_list, 1):
        print(f"\n{'#'*100}")
        print(f"Processing repository {i} of {len(repo_details_list)}: {repo_details.repo_url}")
        print(f"{'#'*100}\n")
        
        repo_name = repo_details.repo_url.split('/')[-1]
        repo_output_dir = os.path.join(base_output_dir, repo_name)
        
        # Download assessed branch
        print(f"\nDownloading assessed branch: {repo_details.assessed_branch}")
        assessed_folder = downloader.download_repo(
            repo_details.repo_url,
            repo_details.assessed_branch,
            repo_output_dir
        )
        if assessed_folder:
            repo_details.assessed_branch_folder = assessed_folder
            print(f"Successfully downloaded to: {assessed_folder}")
        
        # Download transformed branch
        print(f"\nDownloading transformed branch: {repo_details.transformed_branch}")
        transformed_folder = downloader.download_repo(
            repo_details.repo_url,
            repo_details.transformed_branch,
            repo_output_dir
        )
        if transformed_folder:
            repo_details.transformed_branch_folder = transformed_folder
            print(f"Successfully downloaded to: {transformed_folder}")
        
        # Run analysis for both branches
        if repo_details.assessed_branch_folder:
            date_time_assessed_branch = str((int(time.time()) - (1 * 24 * 3600)) * 1000)
            snapshot_label = "pre-transformation"
            print(f"\nAnalyzing assessed branch: {repo_details.assessed_branch}")
            result = cast_client.execute_analysis(
                repo_output_dir,
                repo_details.assessed_branch_folder,
                date_time=date_time_assessed_branch,
                snapshot_label=snapshot_label
            )
            if result != 0:
                print(f"❌ Analysis failed for assessed branch: {repo_details.assessed_branch}")
            else:
                print(f"✅ Analysis completed successfully for assessed branch: {repo_details.assessed_branch}")
        
        if repo_details.transformed_branch_folder:
            print(f"\nAnalyzing transformed branch: {repo_details.transformed_branch}")
            date_time_transformed_branch = str(int(time.time()) * 1000)
            snapshot_label = "post-transformation"
            result = cast_client.execute_analysis(
                repo_output_dir,
                repo_details.transformed_branch_folder,
                date_time=date_time_transformed_branch,
                snapshot_label=snapshot_label
            )
            if result != 0:
                print(f"❌ Analysis failed for transformed branch: {repo_details.transformed_branch}")
            else:
                print(f"✅ Analysis completed successfully for transformed branch: {repo_details.transformed_branch}")

def main():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    if len(sys.argv) != 4:
        print("Usage: python script.py <json_file_path> <github_token> <cast_token>")
        sys.exit(1)

    json_file_path = sys.argv[1]
    github_token = sys.argv[2]
    cast_token = sys.argv[3]

    try:
        process_repositories(json_file_path, github_token, cast_token)
    except Exception as e:
        logging.error(f"An error occurred: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()
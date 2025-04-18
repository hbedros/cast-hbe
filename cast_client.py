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
import yaml
from pathlib import Path


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

class Config:
    def __init__(self, config_path: str):
        with open(config_path, 'r') as f:
            self.config = yaml.safe_load(f)
        
        # Validate required configuration
        self._validate_config()
        # Validate credentials format
        self._validate_credentials()
    
    def _validate_config(self):
        required_fields = {
            'cast': ['base_url', 'company_id', 'login', 'password', 'docker_image'],
            'github': ['token'],
            'amazon_q': ['email', 'portfolio', 'region'],
            'output': ['base_dir']
        }
        
        for section, fields in required_fields.items():
            if section not in self.config:
                raise ValueError(f"Missing required section in config: {section}")
            for field in fields:
                if field not in self.config[section]:
                    raise ValueError(f"Missing required field in {section}: {field}")
    
    def _validate_credentials(self):
        # Validate CAST Highlight credentials
        if not self.config['cast']['login'] or self.config['cast']['login'] == "YOUR_CAST_HIGHLIGHT_EMAIL":
            raise ValueError("CAST Highlight login email is not set")
        if not self.config['cast']['password'] or self.config['cast']['password'] == "YOUR_CAST_HIGHLIGHT_PASSWORD":
            raise ValueError("CAST Highlight password is not set")
        if not '@' in self.config['cast']['login']:
            raise ValueError("CAST Highlight login must be a valid email address")
    
    @property
    def cast_base_url(self) -> str:
        return self.config['cast']['base_url']
    
    @property
    def cast_company_id(self) -> str:
        return self.config['cast']['company_id']
    
    @property
    def cast_login(self) -> str:
        return self.config['cast']['login']
    
    @property
    def cast_password(self) -> str:
        return self.config['cast']['password']
    
    @property
    def cast_docker_image(self) -> str:
        return self.config['cast']['docker_image']
    
    @property
    def github_token(self) -> str:
        return self.config['github']['token']
    
    @property
    def amazon_q_email(self) -> str:
        return self.config['amazon_q']['email']
    
    @property
    def amazon_q_portfolio(self) -> str:
        return self.config['amazon_q']['portfolio']
    
    @property
    def amazon_q_region(self) -> str:
        return self.config['amazon_q']['region']
    
    @property
    def output_base_dir(self) -> str:
        return self.config['output']['base_dir']

class CastApiClient:
    def __init__(self, config: Config, timeout: int = 30):
        self.base_url = config.cast_base_url.rstrip('/')
        self.session = self._create_session()
        self.timeout = timeout
        self.login = config.cast_login
        self.password = config.cast_password
        self.company_id = config.cast_company_id
        self.docker_image = config.cast_docker_image
        self.headers = {
            'Content-Type': 'application/json'
        }

    def _create_session(self) -> requests.Session:
        session = requests.Session()
        adapter = HTTPAdapter(max_retries=3)
        session.mount('http://', adapter)
        session.mount('https://', adapter)
        return session

    def _mask_password(self, command: List[str]) -> str:
        """Mask password in command string for logging."""
        masked_command = []
        for i, arg in enumerate(command):
            if arg == "--password" and i + 1 < len(command):
                masked_command.extend(["--password", "********"])
            else:
                masked_command.append(arg)
        return ' '.join(masked_command)

    def _test_authentication(self) -> bool:
        """Test CAST Highlight authentication before running analysis."""
        try:
            # Create a test Docker command
            test_command = [
                "docker", "run",
                "--rm",
                self.docker_image,
                "--login", self.login,
                "--password", self.password,
                "--testAuth"
            ]
            
            result = subprocess.run(
                test_command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            if result.returncode != 0:
                logging.error("Authentication test failed: %s", result.stderr)
                return False
                
            return True
        except Exception as e:
            logging.error("Error during authentication test: %s", str(e))
            return False

    def execute_analysis(self, work_dir: str, repo_url: str, branch: str, application_id: int, 
                        date_time: int, snapshot_label: str) -> int:
        print(f"\n{'='*80}")
        print(f"Starting analysis:")
        print(f"Repository: {repo_url}")
        print(f"Branch: {branch}")
        print(f"Application ID: {application_id}")
        print(f"Snapshot Label: {snapshot_label}")
        print(f"{'='*80}\n")
        
        if not os.path.exists(work_dir):
            logging.error(f"Working directory does not exist: {work_dir}")
            return 1

        # Test authentication before proceeding
        print("Testing CAST Highlight authentication...")
        if not self._test_authentication():
            logging.error("CAST Highlight authentication failed. Please check your credentials.")
            return 1
        print("Authentication successful!")

        try:
            # Create working directories
            source_dir = os.path.join(work_dir, "source")
            working_dir = os.path.join(work_dir, "working")
            os.makedirs(source_dir, exist_ok=True)
            os.makedirs(working_dir, exist_ok=True)

            # Clone the repository
            repo_name = repo_url.split('/')[-1].replace('.git', '')
            repo_dir = os.path.join(source_dir, repo_name)
            
            if not os.path.exists(repo_dir):
                clone_cmd = [
                    "git", "clone",
                    "--branch", branch,
                    repo_url,
                    repo_dir
                ]
                subprocess.run(clone_cmd, check=True)

            # Create Docker command
            command = [
                "docker", "run",
                "--user", str(os.getuid()),
                "-v", f"{repo_dir}:/sourceDir",
                "-v", f"{working_dir}:/workingDir",
                self.docker_image,
                "--sourceDir", "/sourceDir",
                "--workingDir", "/workingDir",
                "--applicationId", str(application_id),
                "--companyId", self.company_id,
                "--login", self.login,
                "--password", self.password,
                "--snapshotLabel", snapshot_label,
                "--snapshotDatetime", str(date_time)
            ]

            print("Executing command:")
            print(self._mask_password(command))
            print()

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

    def create_application(self, application_name: str) -> Optional[int]:
        """Create a new application in CAST Highlight."""
        url = f"{self.base_url}/applications"  # Base URL already includes /api/v1
        payload = {
            "name": application_name,
            "companyId": self.company_id
        }
        
        try:
            # Use basic authentication
            response = self.session.post(
                url, 
                json=payload, 
                headers=self.headers,
                auth=(self.login, self.password),
                timeout=self.timeout
            )
            response.raise_for_status()
            return response.json().get("id")
        except Exception as e:
            logging.error(f"Error creating application: {str(e)}")
            return None

    def trigger_computation(self, application_id: int) -> bool:
        """Trigger computation for an application."""
        url = f"{self.base_url}/applications/{application_id}/compute"
        
        try:
            response = self.session.post(url, headers=self.headers, timeout=self.timeout)
            response.raise_for_status()
            return True
        except Exception as e:
            logging.error(f"Error triggering computation: {str(e)}")
            return False

    def get_5r_segmentation(self, application_id: int, snapshot_id: int) -> Optional[Dict]:
        """Get 5R segmentation results for a specific snapshot."""
        url = f"{self.base_url}/applications/{application_id}/snapshots/{snapshot_id}/5r-segmentation"
        
        try:
            response = self.session.get(url, headers=self.headers, timeout=self.timeout)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logging.error(f"Error getting 5R segmentation: {str(e)}")
            return None

    def wait_for_computation(self, application_id: int, max_wait_time: int = 3600) -> bool:
        """Wait for computation to complete."""
        url = f"{self.base_url}/applications/{application_id}/status"
        start_time = time.time()
        
        while time.time() - start_time < max_wait_time:
            try:
                response = self.session.get(url, headers=self.headers, timeout=self.timeout)
                response.raise_for_status()
                status = response.json().get("status")
                
                if status == "COMPLETED":
                    return True
                elif status == "FAILED":
                    logging.error("Computation failed")
                    return False
                
                time.sleep(30)  # Wait 30 seconds before checking again
            except Exception as e:
                logging.error(f"Error checking computation status: {str(e)}")
                return False
        
        logging.error("Computation timeout")
        return False

def process_repositories(json_file_path: str, config: Config):
    base_output_dir = config.output_base_dir
    # Create output directory if it doesn't exist
    os.makedirs(base_output_dir, exist_ok=True)

    with open(json_file_path, 'r') as f:
        json_data = f.read()
    
    json_reader = JsonReader(json_data)
    repo_details_list = json_reader.get_repo_details()
    
    downloader = GithubRepoDownloader(config.github_token)
    cast_client = CastApiClient(config)
    
    for i, repo_details in enumerate(repo_details_list, 1):
        print(f"\n{'#'*100}")
        print(f"Processing repository {i} of {len(repo_details_list)}: {repo_details.repo_url}")
        print(f"{'#'*100}\n")
        
        repo_name = repo_details.repo_url.split('/')[-1]
        repo_output_dir = os.path.join(base_output_dir, repo_name)
        # Create repository-specific output directory
        os.makedirs(repo_output_dir, exist_ok=True)
        
        # Create application in CAST Highlight
        print(f"\nCreating application in CAST Highlight: {repo_name}")
        application_id = cast_client.create_application(repo_name)
        if not application_id:
            print(f"❌ Failed to create application for {repo_name}")
            continue
        print(f"✅ Application created with ID: {application_id}")
        
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
            # Use yesterday's date for pre-transformation
            date_time_assessed_branch = str((int(time.time()) - (1 * 24 * 3600)) * 1000)
            snapshot_label = "pre-transformation"
            print(f"\nAnalyzing assessed branch: {repo_details.assessed_branch}")
            result = cast_client.execute_analysis(
                repo_output_dir,
                repo_details.repo_url,
                repo_details.assessed_branch,
                application_id,
                date_time=date_time_assessed_branch,
                snapshot_label=snapshot_label
            )
            if result != 0:
                print(f"❌ Analysis failed for assessed branch: {repo_details.assessed_branch}")
            else:
                print(f"✅ Analysis completed successfully for assessed branch: {repo_details.assessed_branch}")
                
                # Trigger computation and wait for completion
                print("\nTriggering computation for pre-transformation analysis...")
                if cast_client.trigger_computation(application_id):
                    print("Waiting for computation to complete...")
                    if cast_client.wait_for_computation(application_id):
                        print("✅ Computation completed successfully")
                        
                        # Export 5R segmentation
                        print("\nExporting 5R segmentation for pre-transformation...")
                        segmentation = cast_client.get_5r_segmentation(application_id, int(date_time_assessed_branch))
                        if segmentation:
                            output_file = os.path.join(repo_output_dir, "pre_transformation_5r.json")
                            with open(output_file, 'w') as f:
                                json.dump(segmentation, f, indent=2)
                            print(f"✅ 5R segmentation exported to {output_file}")
                        else:
                            print("❌ Failed to export 5R segmentation")
                    else:
                        print("❌ Computation failed or timed out")
                else:
                    print("❌ Failed to trigger computation")
        
        if repo_details.transformed_branch_folder:
            # Use current date for post-transformation
            date_time_transformed_branch = str(int(time.time()) * 1000)
            snapshot_label = "post-transformation"
            print(f"\nAnalyzing transformed branch: {repo_details.transformed_branch}")
            result = cast_client.execute_analysis(
                repo_output_dir,
                repo_details.repo_url,
                repo_details.transformed_branch,
                application_id,
                date_time=date_time_transformed_branch,
                snapshot_label=snapshot_label
            )
            if result != 0:
                print(f"❌ Analysis failed for transformed branch: {repo_details.transformed_branch}")
            else:
                print(f"✅ Analysis completed successfully for transformed branch: {repo_details.transformed_branch}")
                
                # Trigger computation and wait for completion
                print("\nTriggering computation for post-transformation analysis...")
                if cast_client.trigger_computation(application_id):
                    print("Waiting for computation to complete...")
                    if cast_client.wait_for_computation(application_id):
                        print("✅ Computation completed successfully")
                        
                        # Export 5R segmentation
                        print("\nExporting 5R segmentation for post-transformation...")
                        segmentation = cast_client.get_5r_segmentation(application_id, int(date_time_transformed_branch))
                        if segmentation:
                            output_file = os.path.join(repo_output_dir, "post_transformation_5r.json")
                            with open(output_file, 'w') as f:
                                json.dump(segmentation, f, indent=2)
                            print(f"✅ 5R segmentation exported to {output_file}")
                        else:
                            print("❌ Failed to export 5R segmentation")
                    else:
                        print("❌ Computation failed or timed out")
                else:
                    print("❌ Failed to trigger computation")

def main():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    if len(sys.argv) != 3:
        print("Usage: python script.py <config_file_path> <json_file_path>")
        sys.exit(1)

    config_path = sys.argv[1]
    json_file_path = sys.argv[2]

    try:
        # Load configuration
        config = Config(config_path)
        
        # Process repositories
        process_repositories(json_file_path, config)
    except Exception as e:
        logging.error(f"An error occurred: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()
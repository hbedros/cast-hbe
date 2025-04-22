import os
import logging
import requests
import yaml
import json
import subprocess
import time
import sys
from requests.auth import HTTPBasicAuth
from threading import Thread, Event

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class Spinner:
    """Simple spinner animation for long-running operations"""
    def __init__(self):
        self.spinner_chars = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏']
        self.stop_event = Event()
        self.spinner_thread = None

    def start(self, message):
        """Start the spinner with a message"""
        self.stop_event.clear()
        self.spinner_thread = Thread(target=self._spin, args=(message,))
        self.spinner_thread.start()

    def stop(self):
        """Stop the spinner"""
        self.stop_event.set()
        if self.spinner_thread:
            self.spinner_thread.join()
        sys.stdout.write('\r' + ' ' * 100 + '\r')  # Clear the line
        sys.stdout.flush()

    def _spin(self, message):
        """Run the spinner animation"""
        i = 0
        while not self.stop_event.is_set():
            sys.stdout.write(f'\r{self.spinner_chars[i]} {message}')
            sys.stdout.flush()
            time.sleep(0.1)
            i = (i + 1) % len(self.spinner_chars)

def load_config():
    """Load configuration from YAML file"""
    spinner = Spinner()
    spinner.start("Loading configuration from config.yaml...")
    try:
        with open('config.yaml', 'r') as file:
            config = yaml.safe_load(file)
            spinner.stop()
            logging.info("✓ Configuration loaded successfully")
            return config
    except Exception as e:
        spinner.stop()
        logging.error(f"✗ Failed to load config.yaml: {e}")
        return None

def load_input_json():
    """Load input JSON file"""
    spinner = Spinner()
    spinner.start("Loading input data from test_input.json...")
    try:
        with open('test_input.json', 'r') as file:
            data = json.load(file)
            spinner.stop()
            logging.info("✓ Input data loaded successfully")
            return data
    except Exception as e:
        spinner.stop()
        logging.error(f"✗ Failed to load test_input.json: {e}")
        return None

def create_application(config, input_data):
    """Create a new application in CAST Highlight"""
    spinner = Spinner()
    try:
        # Get credentials from config
        cast_config = config['cast']
        company_id = cast_config['company_id']
        url = f"{cast_config['base_url']}/domains/{company_id}/applications"
        
        # Get repository name from input JSON
        repo_name = input_data['repositories'][0]['name']
        app_name = f"{repo_name}-analysis"
        
        payload = [{
            "name": app_name,
            "domains": [{"id": int(company_id)}]
        }]

        headers = {
            'Content-Type': 'application/json'
        }

        logging.info(f"Creating application '{app_name}' in domain {company_id}")
        spinner.start("Sending request to CAST Highlight API...")

        response = requests.post(
            url,
            headers=headers,
            auth=HTTPBasicAuth(cast_config['login'], cast_config['password']),
            json=payload,
            verify=False
        )
        
        spinner.stop()
        if response.status_code == 200:
            app_data = response.json()
            if app_data.get('result') and app_data['result'][0].get('id'):
                app_id = app_data['result'][0]['id']
                logging.info(f"✓ Successfully created application with ID: {app_id}")
                return app_id
            else:
                logging.error(f"✗ Unexpected response format: {app_data}")
                return None
        else:
            logging.error(f"✗ Failed to create application. Status code: {response.status_code}")
            logging.error(f"✗ Response: {response.text}")
            return None
            
    except Exception as e:
        spinner.stop()
        logging.error(f"✗ Error creating application: {e}")
        return None

def scan_repository(app_id, config, input_data):
    """Scan a GitHub repository using CAST Highlight CLI"""
    spinner = Spinner()
    try:
        cast_config = config['cast']
        repo_url = input_data['repositories'][0]['repositoryLocation']['url']
        
        # Construct the CLI command to use Docker's internal directories
        command = [
            "docker", "run", "--rm",
            "-v", "/tmp:/workingDir",
            cast_config['docker_image'],
            "--gitUrl", repo_url,
            "--sourceDir", "/app",  # Use Docker container's internal directory
            "--workingDir", "/workingDir",
            "--applicationId", str(app_id),
            "--companyId", cast_config['company_id'],
            "--login", cast_config['login'],
            "--password", cast_config['password']
        ]
        
        logging.info("Starting repository scan...")
        spinner.start("Running CAST Highlight analysis (this may take several minutes)...")
        
        # Run the command
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=True
        )
        
        spinner.stop()
        logging.info("✓ Scan completed successfully")
        logging.info(result.stdout)
        return True
        
    except subprocess.CalledProcessError as e:
        spinner.stop()
        logging.error(f"✗ Scan failed with error: {e}")
        logging.error(f"✗ Command output: {e.stdout}")
        logging.error(f"✗ Command error: {e.stderr}")
        return False
    except Exception as e:
        spinner.stop()
        logging.error(f"✗ Error during scan: {e}")
        return False

def main():
    logging.info("=" * 80)
    logging.info("Starting CAST Highlight Analysis Process")
    logging.info("=" * 80)
    
    # Load configuration
    config = load_config()
    if not config:
        return
    
    # Load input JSON
    input_data = load_input_json()
    if not input_data:
        return
    
    # Create application
    app_id = create_application(config, input_data)
    if not app_id:
        return
    
    # Scan repository
    if not scan_repository(app_id, config, input_data):
        return
    
    logging.info("=" * 80)
    logging.info("✓ Process completed successfully")
    logging.info("=" * 80)

if __name__ == "__main__":
    main() 
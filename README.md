# CAST Highlight Analysis Tool

This tool automates the process of analyzing GitHub repositories using CAST Highlight. It creates applications in CAST Highlight and runs static code analysis on the specified repositories using Docker containers with the official CAST Highlight CLI image.

## Prerequisites

- Python 3.x
- Docker Desktop
- CAST Highlight account credentials
- Internet connection for pulling the CAST Highlight Docker image

## Installation

1. Clone this repository:
```bash
git clone <repository-url>
cd cast-hbe
```

2. Install required Python packages:
```bash
pip install -r requirements.txt
```

3. Set up your configuration:
   - Copy `config.yaml.example` to `config.yaml`:
   ```bash
   cp config.yaml.example config.yaml
   ```
   - Edit `config.yaml` with your credentials:
   ```yaml
   cast:
     base_url: "https://rpa.casthighlight.com"
     company_id: "YOUR_COMPANY_ID"
     token: "YOUR_HIGHLIGHT_TOKEN"
     docker_image: "casthighlight/hl-cli"

   github:
     token: "YOUR_GITHUB_TOKEN"

   amazon_q:
     email: "YOUR_AMAZON_Q_EMAIL"
     portfolio: "AmazonQ"
     region: "us-east-1"

   output:
     base_dir: "/tmp/output"
   ```

4. Create a `.env` file with your CAST Highlight credentials:
```bash
CAST_BASE_URL=https://rpa.casthighlight.com/WS2
CAST_COMPANY_ID=your_company_id
CAST_LOGIN=your_login
CAST_PASSWORD=your_password
CAST_DOCKER_IMAGE=casthighlight/hl-cli
```

## Configuration

1. Create a `test_input.json` file with your repository information:
```json
{
    "repositories": [
        {
            "name": "repository-name",
            "repositoryLocation": {
                "url": "https://github.com/username/repository.git"
            }
        }
    ]
}
```

You can add multiple repositories to the JSON array to analyze them in sequence.

## Usage

1. Make sure Docker Desktop is running (the script will use the official CAST Highlight Docker image)

2. Run the analysis script:
```bash
python cast_client.py
```

The script will:
- Create a new application in CAST Highlight for each repository
- Pull and run the CAST Highlight CLI Docker container
- Mount necessary directories for analysis
- Run static code analysis inside the Docker container
- Display progress with a spinner animation
- Show detailed logs of the process

## Docker Integration

The tool uses Docker to:
- Run the CAST Highlight CLI in an isolated environment
- Handle all dependencies automatically
- Ensure consistent analysis results
- Mount local directories for analysis workspace
- Clean up automatically after analysis completion

## Error Handling

The script includes comprehensive error handling and will:
- Validate all configuration before starting
- Show clear error messages if something goes wrong
- Continue processing other repositories if one fails
- Display detailed logs for troubleshooting

## Logging

The tool provides detailed logging with:
- Timestamps for each operation
- Success/failure indicators (✓/✗)
- Progress information for long-running operations
- Clear separation between different repositories being processed

## Support

For issues or questions about:
- CAST Highlight API: Contact CAST Support
- This tool: Create an issue in the repository
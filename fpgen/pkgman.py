import os
import tempfile
import zipfile
from pathlib import Path
from typing import Any, Dict

import click
import httpx

from fpgen.exceptions import MissingRelease

GITHUB_REPO = 'scrapfly/fingerprint-generator'
DATA_DIR = Path(__file__).parent / 'data'


class ModelPuller:
    """
    Pulls the model from GitHub and extracts it to the data directory.
    """

    def __init__(self) -> None:
        self.api_url = f"https://api.github.com/repos/{GITHUB_REPO}/releases"

    def check_asset(self, asset: Dict) -> Any:
        """
        Compare the asset to determine if it's the desired asset.

        Args:
            asset: Asset information from GitHub API

        Returns:
            Any: Data to be returned if this is the desired asset, or None/False if not
        """
        url = asset.get('browser_download_url')
        if url and url.endswith('.zip'):
            return url

    def missing_asset_error(self) -> None:
        """
        Raise a MissingRelease exception if no release is found.
        """
        raise MissingRelease(f"Could not find a release asset in {GITHUB_REPO}.")

    def get_asset(self) -> Any:
        """
        Fetch the latest release from the GitHub API.
        Gets the first asset that returns a truthy value from check_asset.
        """
        resp = httpx.get(self.api_url, timeout=20, verify=False)
        resp.raise_for_status()

        releases = resp.json()

        for release in releases:
            for asset in release['assets']:
                if data := self.check_asset(asset):
                    return data

        self.missing_asset_error()

    def download(self):
        """
        Download the model from GitHub and extract it to the data directory.
        """
        # Pull form a custom source, or the GitHub API

        url = os.getenv('FPGEN_MODEL_URL')
        if url:
            click.echo(f"Fetching model files from {url}...")
        else:
            click.echo("Fetching model files from GitHub...")
            url = self.get_asset()

        # Optionally get the model password
        password = os.getenv('FPGEN_MODEL_PASSWORD')
        if password:
            password = password.encode()

        # Stream to tempfile then extract using zipfile
        with tempfile.NamedTemporaryFile(delete=False) as temp_file:
            with httpx.stream(
                'GET', url, timeout=20, verify=False, follow_redirects=True
            ) as r:  # nosec
                for chunk in r.iter_bytes():
                    temp_file.write(chunk)
                temp_file.flush()
            temp_file.close()

            click.echo(f"Extracting to {DATA_DIR}...")
            with zipfile.ZipFile(temp_file.name) as z:
                z.extractall(DATA_DIR, pwd=password)

            os.unlink(temp_file.name)


def download_model():
    """
    Call the model puller to download files
    """
    ModelPuller().download()


def assert_downloaded(*files: Path):
    """
    Checks if the model files are downloaded
    """
    if __is_module__():
        return  # Skip if running as a module
    if all(file.with_suffix(file.suffix + '.zst').exists() for file in files):
        return
    if all(file.exists() for file in files):
        return

    # Automatically fetch the model if not found
    ModelPuller().download()


def __is_module__() -> bool:
    '''
    Checks if fpgen is being ran as a module
    '''
    return bool(os.getenv('FPGEN_NO_AUTO_DOWNLOAD'))

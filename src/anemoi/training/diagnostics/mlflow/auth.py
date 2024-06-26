import logging
import os
import time
from getpass import getpass

import requests
from anemoi.utils.config import load_config
from anemoi.utils.config import save_config
from requests.exceptions import HTTPError

LOG = logging.getLogger(__name__)


class TokenAuthenticator:
    def __init__(
        self,
        uri="https://mlflow-test.ecmwf.int",
        refresh_expire_days=29,
        enabled=True,
    ):
        self.uri = uri
        self.refresh_expire_days = refresh_expire_days
        self.enabled = enabled

        self.config_file = "mlflow-token.json"
        config = load_config(self.config_file)

        self.refresh_token = config.get("refresh_token")
        self.refresh_expires = config.get("refresh_expires", 0)
        self.access_token = None
        self.access_expires = 0

    def __call__(self):
        self.authenticate()

    def login(self):
        if self.refresh_token and self.refresh_expires >= time.time():
            new_refresh_token = self._token_login(self.refresh_token)
        else:
            username = input("Username: ")
            password = getpass("Password: ")
            new_refresh_token = self._credential_login(username, password)

        if new_refresh_token:
            self.refresh_token = new_refresh_token
            self._save_config(new_refresh_token)
            LOG.info("Successfully authenticated with MLflow. Happy logging!")
        else:
            raise ValueError("No refresh token received.")

    def authenticate(self):
        if not self.enabled:
            return

        if self.access_expires > time.time():
            return

        if not self.refresh_token:
            raise RuntimeError("You are not logged in to MLFlow. Please log in first.")

        self.access_token, self.access_expires = self._get_access_token()

        LOG.debug("Access token refreshed.")

        os.environ["MLFLOW_TRACKING_TOKEN"] = self.access_token

    def _save_config(self, refresh_token: str):
        refresh_expires = time.time() + (self.refresh_expire_days * 24 * 60 * 60)
        config = {
            "refresh_token": refresh_token,
            "refresh_expires": int(refresh_expires),
        }
        save_config(self.config_file, config)

    def _credential_login(self, username: str, password: str):
        payload = {"username": username, "password": password}
        response = self._request("newtoken", payload)

        return response.get("refresh_token")

    def _token_login(self, refresh_token: str):
        payload = {"refresh_token": refresh_token}
        response = self._request("refreshtoken", payload)

        return response.get("refresh_token")

    def _get_access_token(self):
        payload = {"refresh_token": self.refresh_token}
        response = self._request("refreshtoken", payload)

        token = response.get("access_token")
        expires_in = response.get("expires_in")

        expires = time.time() + (expires_in * 0.7)  # some buffer time

        return token, expires

    def _request(self, path: str, payload: dict):

        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
        }

        try:
            response = requests.post(f"{self.uri}/{path}", headers=headers, json=payload)
            response.raise_for_status()
            response_json = response.json()

            return response_json["response"]
        except HTTPError as http_err:
            LOG.error(f"HTTP error occurred: {http_err}")
            raise
        except Exception as err:
            LOG.error(f"Other error occurred: {err}")
            raise

from datetime import datetime, timedelta, timezone
from io import BytesIO
from typing import Dict, List, Optional, Set
from zipfile import ZipFile

import boto3
from botocore.exceptions import ClientError

from app.services.filename_manager import resolve_conflict_name
from app.utils.validators import sanitize_filename


class S3Manager:
    def __init__(self, bucket: str, region: str, aws_role: str = "", role_session_name: str = "netai-session"):
        self.bucket = bucket
        self.region = region
        self.aws_role = aws_role.strip()
        self.role_session_name = role_session_name or "netai-session"
        self._base_session = boto3.session.Session(region_name=region)
        self._s3_client = None
        self._sts_client = None
        self._assumed_expiration: Optional[datetime] = None
        self._assumed_credentials: Optional[Dict[str, str]] = None

    def bootstrap_assumed_role(self) -> None:
        if self.aws_role:
            self._refresh_assumed_credentials(force=True)

    def _sts(self):
        if self._sts_client is None:
            self._sts_client = self._base_session.client("sts", region_name=self.region)
        return self._sts_client

    def _credentials_expiring_soon(self) -> bool:
        if not self._assumed_expiration:
            return True
        return datetime.now(timezone.utc) >= (self._assumed_expiration - timedelta(minutes=5))

    def _refresh_assumed_credentials(self, force: bool = False) -> None:
        if not self.aws_role:
            return
        if not force and not self._credentials_expiring_soon():
            return

        response = self._sts().assume_role(
            RoleArn=self.aws_role,
            RoleSessionName=self.role_session_name,
        )
        creds = response["Credentials"]
        self._assumed_credentials = {
            "aws_access_key_id": creds["AccessKeyId"],
            "aws_secret_access_key": creds["SecretAccessKey"],
            "aws_session_token": creds["SessionToken"],
        }
        self._assumed_expiration = creds["Expiration"]
        self._s3_client = boto3.client("s3", region_name=self.region, **self._assumed_credentials)

    def _client(self):
        if self.aws_role:
            self._refresh_assumed_credentials()
            return self._s3_client

        if self._s3_client is None:
            self._s3_client = self._base_session.client("s3", region_name=self.region)
        return self._s3_client

    def list_config_folders(self) -> List[str]:
        if not self.bucket:
            return []

        paginator = self._client().get_paginator("list_objects_v2")
        folders = set()
        for page in paginator.paginate(Bucket=self.bucket, Delimiter="/"):
            for pref in page.get("CommonPrefixes", []):
                prefix = pref.get("Prefix", "").rstrip("/")
                if prefix:
                    folders.add(prefix)
        return sorted(folders)

    def ensure_folder(self, config_folder: str) -> None:
        key = f"{config_folder}/configs/"
        self._client().put_object(Bucket=self.bucket, Key=key, Body=b"")

    def _list_existing_files(self, config_folder: str) -> Set[str]:
        prefix = f"{config_folder}/configs/"
        paginator = self._client().get_paginator("list_objects_v2")
        existing: Set[str] = set()
        for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix):
            for obj in page.get("Contents", []):
                key = obj["Key"]
                if key.endswith("/"):
                    continue
                existing.add(key[len(prefix) :])
        return existing

    def _exists_key(self, key: str) -> bool:
        try:
            self._client().head_object(Bucket=self.bucket, Key=key)
            return True
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code")
            if code in {"404", "NoSuchKey", "NotFound"}:
                return False
            raise

    def upload_file(self, config_folder: str, file_storage) -> Dict[str, object]:
        original_name = sanitize_filename(file_storage.filename)
        prefix = f"{config_folder}/configs/"

        existing = self._list_existing_files(config_folder)
        final_name, conflict = resolve_conflict_name(original_name, existing)

        max_attempts = 20
        for _ in range(max_attempts):
            key = f"{prefix}{final_name}"
            if self._exists_key(key):
                existing.add(final_name)
                final_name, conflict = resolve_conflict_name(original_name, existing)
                continue

            file_storage.stream.seek(0)
            self._client().upload_fileobj(file_storage.stream, self.bucket, key)
            return {
                "original_name": original_name,
                "final_name": final_name,
                "s3_key": key,
                "conflict_resolved": conflict,
            }

        raise RuntimeError("Unable to upload file due to repeated conflicts")

    def get_snapshot_zip_data(self, config_folder: str) -> bytes:
        prefix = f"{config_folder}/"
        paginator = self._client().get_paginator("list_objects_v2")

        zip_buffer = BytesIO()
        wrote_files = False

        with ZipFile(zip_buffer, "w") as zip_file:
            for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix):
                for obj in page.get("Contents", []):
                    key = obj.get("Key", "")
                    if not key or key.endswith("/"):
                        continue

                    relative = key[len(prefix) :] if key.startswith(prefix) else key
                    if not relative:
                        continue

                    if relative.startswith("configs/"):
                        config_rel = relative[len("configs/") :]
                    else:
                        config_rel = relative

                    if not config_rel:
                        continue

                    response = self._client().get_object(Bucket=self.bucket, Key=key)
                    payload = response["Body"].read()
                    zip_path = f"snapshot/configs/{config_rel}"
                    zip_file.writestr(zip_path, payload)
                    wrote_files = True

        if not wrote_files:
            raise RuntimeError(f"No config files found in folder '{config_folder}'")

        return zip_buffer.getvalue()

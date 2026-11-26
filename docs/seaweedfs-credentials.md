# SeaweedFS credentials

Docker Compose uses `FILE_SEAWEEDFS_S3_ACCESS_KEY` and
`FILE_SEAWEEDFS_S3_SECRET_KEY` for both the file service and the bundled S3
server. For a deployment, set both to strong, random values in the environment
file that Compose uses. The defaults are for local development only.

The filer generates its S3 configuration in memory at container startup. You do
not need to create or edit `storage/seaweedfs/s3.json`. If you upgrade an
existing deployment, make sure the Compose variables contain the intended pair.
The filer no longer reads the old file.

To change the credentials on a running deployment, change both values and
recreate the filer and the file service. Use the same Compose file and options
that you use to start the stack. For example, for the source stack:

```sh
docker compose -f docker-compose.src.yml up -d --no-deps \
  seaweedfs-filer file-service
docker compose -f docker-compose.src.yml exec nginx nginx -s reload
```

This briefly interrupts file access. It does not change stored files or their
metadata. After the services start, retry a download.

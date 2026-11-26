#!/bin/sh
set -eu

: "${SEAWEEDFS_S3_ACCESS_KEY:?Set the S3 access key}"
: "${SEAWEEDFS_S3_SECRET_KEY:?Set the S3 secret key}"

config=$(mktemp "$1/s3.XXXXXX")
shift

# SeaweedFS 3.95 needs a JSON file. Use the image's BusyBox awk to encode
# credentials without expanding them as shell or awk source.
LC_ALL=C awk '
  function json_string(value,    i, char, result, controls) {
    for (i = 1; i < 32; i++) {
      controls[sprintf("%c", i)] = sprintf("\\u%04x", i)
    }
    result = "\""
    for (i = 1; i <= length(value); i++) {
      char = substr(value, i, 1)
      if (char == "\"" || char == "\\") {
        result = result "\\" char
      } else if (char in controls) {
        result = result controls[char]
      } else {
        result = result char
      }
    }
    return result "\""
  }
  BEGIN {
    print "{\"identities\":[{\"name\":\"file-service\",\"credentials\":[{"
    printf "\"accessKey\":%s,\"secretKey\":%s", \
      json_string(ENVIRON["SEAWEEDFS_S3_ACCESS_KEY"]), \
      json_string(ENVIRON["SEAWEEDFS_S3_SECRET_KEY"])
    print "}],\"actions\":[\"Read\",\"Write\",\"List\",\"Tagging\",\"Admin\"]}]}"
  }
' > "$config"

exec "$@" "-s3.config=$config"
